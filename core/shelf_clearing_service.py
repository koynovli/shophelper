from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .media_upload import save_task_photo
from .models import (
    EquipmentSlot,
    PlacementTask,
    Planogram,
    ProductBatch,
    ShelfClearingTask,
    User,
)
from .placement_sync import peek_fefo_batch_id, reconcile_planogram, return_to_batch
from .slot_inventory_sync import suppress_operational_side_effects, sync_inventory_from_slot
from .ws_broadcast import broadcast_task_pool

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


class ShelfClearingError(ValidationError):
    pass


ACTIVE_PLACEMENT_STATUSES = (
    PlacementTask.Status.CREATED,
    PlacementTask.Status.PENDING,
    PlacementTask.Status.IN_PROGRESS,
)

ACTIVE_CLEARING_STATUSES = (
    ShelfClearingTask.Status.CREATED,
    ShelfClearingTask.Status.PENDING,
    ShelfClearingTask.Status.IN_PROGRESS,
)


def _resolve_return_batch(planogram: Planogram, product_id: int) -> int | None:
    last_completed = (
        PlacementTask.objects.filter(
            planogram=planogram,
            product_id=product_id,
            status=PlacementTask.Status.COMPLETED,
            batch_id__isnull=False,
        )
        .order_by("-completed_at", "-pk")
        .first()
    )
    if last_completed and last_completed.batch_id:
        return last_completed.batch_id
    return peek_fefo_batch_id(product_id)


def create_shelf_clearing_task(manager: AbstractUser, slot_id: int) -> ShelfClearingTask:
    if getattr(manager, "role", None) != User.Role.ADMIN:
        raise ShelfClearingError("Создавать задания на уборку может только менеджер.")

    with transaction.atomic():
        slot = (
            EquipmentSlot.objects.select_for_update()
            .select_related("equipment", "equipment__zone")
            .prefetch_related("planograms__product")
            .get(pk=slot_id)
        )
        qty = int(slot.current_qty or 0)
        if qty <= 0:
            raise ShelfClearingError("На слоте нет товара для уборки на склад.")

        planogram = slot.planograms.select_related("product").first()
        if planogram is None:
            raise ShelfClearingError(
                "На слоте нет планограммы — невозможно определить товар для уборки."
            )

        existing = ShelfClearingTask.objects.filter(
            slot_id=slot.pk,
            status__in=ACTIVE_CLEARING_STATUSES,
        ).first()
        if existing is not None:
            raise ShelfClearingError("По этому слоту уже есть активное задание на уборку.")

        batch_id = _resolve_return_batch(planogram, planogram.product_id)
        if batch_id is None:
            raise ShelfClearingError(
                "Нет партии на складе для возврата товара. Проверьте приёмку."
            )

        task = ShelfClearingTask.objects.create(
            planogram=planogram,
            slot=slot,
            product=planogram.product,
            equipment=slot.equipment,
            quantity=qty,
            batch_id=batch_id,
            status=ShelfClearingTask.Status.CREATED,
        )

    broadcast_task_pool(
        "shelf_clearing_task.created",
        {
            "id": str(task.pk),
            "product_name": task.product.name,
            "quantity": task.quantity,
            "equipment_name": task.equipment.name,
        },
    )
    return task


def accept_shelf_clearing_task(task_id: int, user: AbstractUser) -> ShelfClearingTask:
    with transaction.atomic():
        task = ShelfClearingTask.objects.select_for_update().get(pk=task_id)
        if task.status not in (
            ShelfClearingTask.Status.CREATED,
            ShelfClearingTask.Status.PENDING,
        ):
            raise ShelfClearingError("Задание можно взять только в статусе CREATED.")
        if task.assigned_to_id and task.assigned_to_id != user.pk:
            raise ShelfClearingError("Задание назначено другому сотруднику.")
        task.assigned_to = user
        task.status = ShelfClearingTask.Status.IN_PROGRESS
        task.save(update_fields=["assigned_to", "status"])

    broadcast_task_pool(
        "shelf_clearing_task.updated",
        {"id": str(task.pk), "status": task.status},
    )
    return task


def complete_shelf_clearing_task(
    task_id: int,
    user: AbstractUser,
    photo_file=None,
    *,
    raw_code: str | None = None,
    store_id: int | None = None,
) -> ShelfClearingTask:
    with transaction.atomic():
        task = ShelfClearingTask.objects.select_for_update().select_related(
            "product", "slot", "equipment", "equipment__zone"
        ).get(pk=task_id)
        if task.status != ShelfClearingTask.Status.IN_PROGRESS:
            raise ShelfClearingError("Завершить можно только задание IN_PROGRESS.")
        if task.assigned_to_id and task.assigned_to_id != user.pk:
            raise ShelfClearingError("Задание назначено другому сотруднику.")

        from .scan_service import validate_task_product_scan

        try:
            validate_task_product_scan(
                task_product_id=task.product_id,
                raw_code=raw_code or "",
                store_id=store_id or task.equipment.zone.store_id,
                expected_batch_id=task.batch_id,
            )
        except ValueError as exc:
            raise ShelfClearingError(str(exc)) from exc

        slot = EquipmentSlot.objects.select_for_update().get(pk=task.slot_id)
        on_shelf = int(slot.current_qty or 0)
        if on_shelf <= 0:
            raise ShelfClearingError("На слоте уже нет товара.")
        move_qty = min(int(task.quantity), on_shelf)

        with suppress_operational_side_effects():
            try:
                return_to_batch(task.product_id, move_qty, task.batch_id)
            except ValueError as exc:
                raise ShelfClearingError(str(exc)) from exc

            slot.current_qty = max(0, on_shelf - move_qty)
            slot.save(update_fields=["current_qty"])
            store_id = task.equipment.zone.store_id
            sync_inventory_from_slot(slot, task.product_id, store_id)

        if task.planogram_id:
            PlacementTask.objects.filter(
                planogram_id=task.planogram_id,
                status__in=ACTIVE_PLACEMENT_STATUSES,
            ).update(status=PlacementTask.Status.CANCELLED)

        update_fields = ["status", "completed_at", "quantity"]
        task.quantity = move_qty
        if photo_file is not None:
            task.photo_url = save_task_photo(photo_file, prefix="clearing_reports")
            update_fields.append("photo_url")
        task.status = ShelfClearingTask.Status.COMPLETED
        task.completed_at = timezone.now()
        task.save(update_fields=update_fields)

        if task.planogram_id:
            reconcile_planogram(task.planogram)

    broadcast_task_pool(
        "shelf_clearing_task.completed",
        {"id": str(task.pk), "status": task.status},
    )
    return task


def cancel_shelf_clearing_task(task_id: int, manager: AbstractUser) -> ShelfClearingTask:
    if getattr(manager, "role", None) != User.Role.ADMIN:
        raise ShelfClearingError("Отменять задания может только менеджер.")
    with transaction.atomic():
        task = ShelfClearingTask.objects.select_for_update().get(pk=task_id)
        if task.status in (
            ShelfClearingTask.Status.COMPLETED,
            ShelfClearingTask.Status.CANCELLED,
        ):
            raise ShelfClearingError("Задание уже закрыто.")
        task.status = ShelfClearingTask.Status.CANCELLED
        task.save(update_fields=["status"])

    broadcast_task_pool(
        "shelf_clearing_task.updated",
        {"id": str(task.pk), "status": task.status},
    )
    return task
