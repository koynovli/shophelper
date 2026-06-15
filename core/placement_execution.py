from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .media_upload import save_task_photo
from .models import EquipmentSlot, PlacementTask, ProductBatch
from .placement_scan_service import (
    PlacementScanError,
    ensure_placement_scans_complete,
    scanned_amount_for_task,
)
from .product_units import format_quantity, product_stores_weight
from .placement_sync import (
    available_batch_qty,
    deduct_from_batches,
    reconcile_planogram,
)
from .slot_inventory_sync import sync_inventory_from_slot
from .spatial_engine import refresh_slot_max_capacity
from .ws_broadcast import broadcast_task_pool

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


class PlacementExecutionError(ValidationError):
    pass


def _get_task_for_update(task_id: int) -> PlacementTask:
    return (
        PlacementTask.objects.select_for_update()
        .select_related(
            "product",
            "equipment",
            "equipment__zone",
            "equipment__zone__store",
            "planogram",
            "planogram__slot",
            "batch",
        )
        .get(pk=task_id)
    )


def _ensure_batch_availability(product_id: int, qty: int, product=None) -> None:
    avail = available_batch_qty(product_id)
    if avail < qty:
        label = format_quantity(product, qty) if product else f"{qty}"
        avail_label = format_quantity(product, avail) if product else f"{avail}"
        raise PlacementExecutionError(
            f"На складе недостаточно годных партий (доступно {avail_label} из {label}). "
            "Проверьте приёмку или срок годности партий."
        )


def accept_placement_task(task_id: int, user: AbstractUser) -> PlacementTask:
    with transaction.atomic():
        task = _get_task_for_update(task_id)
        if task.status not in (PlacementTask.Status.CREATED, PlacementTask.Status.PENDING):
            raise PlacementExecutionError("Задачу можно взять только в статусе CREATED.")
        if task.assigned_to_id and task.assigned_to_id != user.pk:
            raise PlacementExecutionError("Задача уже назначена другому сотруднику.")
        if task.planogram_id and PlacementTask.objects.filter(
            planogram_id=task.planogram_id,
            status=PlacementTask.Status.IN_PROGRESS,
        ).exclude(pk=task.pk).exists():
            raise PlacementExecutionError(
                "По этой планограмме уже выполняется другая задача выкладки."
            )
        _ensure_batch_availability(task.product_id, int(task.quantity), task.product)
        task.assigned_to = user
        task.status = PlacementTask.Status.IN_PROGRESS
        task.save(update_fields=["assigned_to", "status"])
    broadcast_task_pool("placement_task.updated", {"id": task.pk, "status": task.status})
    return task


def complete_placement_task(task_id: int, user: AbstractUser, photo_file) -> PlacementTask:
    with transaction.atomic():
        task = _get_task_for_update(task_id)
        if task.status != PlacementTask.Status.IN_PROGRESS:
            raise PlacementExecutionError("Завершить можно только задачу IN_PROGRESS.")
        if task.assigned_to_id and task.assigned_to_id != user.pk:
            raise PlacementExecutionError("Задача назначена другому сотруднику.")

        try:
            ensure_placement_scans_complete(task)
        except PlacementScanError as exc:
            raise PlacementExecutionError(str(exc)) from exc

        if product_stores_weight(task.product):
            qty = scanned_amount_for_task(task)
            _ensure_batch_availability(task.product_id, qty, task.product)
            deducted, primary_batch_id = deduct_from_batches(task.product_id, qty)
            if deducted < qty:
                raise PlacementExecutionError(
                    f"На складе недостаточно годных партий "
                    f"(доступно {format_quantity(task.product, deducted)} "
                    f"из {format_quantity(task.product, qty)}). "
                    "Проверьте приёмку или срок годности партий."
                )
        elif task.product.is_marked:
            qty = int(task.quantity)
            scan_batches = list(
                task.scans.exclude(batch_id__isnull=True).values_list("batch_id", flat=True)
            )
            if len(scan_batches) < qty:
                raise PlacementExecutionError("Не все отсканированные партии привязаны.")
            for batch_id in scan_batches:
                batch = ProductBatch.objects.select_for_update().get(pk=batch_id)
                batch.deduct_quantity(1)
            from .placement_sync import sync_stock_item_from_batches

            sync_stock_item_from_batches(task.product_id)
            primary_batch_id = scan_batches[0] if scan_batches else task.batch_id
        else:
            qty = int(task.quantity)
            _ensure_batch_availability(task.product_id, qty, task.product)
            deducted, primary_batch_id = deduct_from_batches(task.product_id, qty)
            if deducted < qty:
                raise PlacementExecutionError(
                    f"На складе недостаточно годных партий "
                    f"(доступно {format_quantity(task.product, deducted)} "
                    f"из {format_quantity(task.product, qty)}). "
                    "Проверьте приёмку или срок годности партий."
                )

        slot = EquipmentSlot.objects.select_for_update().get(pk=task.planogram.slot_id)
        cap = refresh_slot_max_capacity(slot, task.product)
        new_qty = int(slot.current_qty) + qty
        slot.current_qty = min(new_qty, cap) if cap > 0 else new_qty
        slot.save(update_fields=["current_qty"])
        store_id = task.equipment.zone.store_id
        sync_inventory_from_slot(slot, task.product_id, store_id)

        update_fields = ["batch", "status", "completed_at"]
        if photo_file is not None:
            task.photo_url = save_task_photo(photo_file, prefix="placement_reports")
            update_fields.append("photo_url")
        task.batch_id = primary_batch_id or task.batch_id
        task.status = PlacementTask.Status.COMPLETED
        task.completed_at = timezone.now()
        task.save(update_fields=update_fields)

        if task.planogram_id:
            reconcile_planogram(task.planogram)

    broadcast_task_pool("placement_task.completed", {"id": task.pk, "status": task.status})
    return task


def fail_placement_task(task_id: int, user: AbstractUser, reason: str = "") -> PlacementTask:
    with transaction.atomic():
        task = _get_task_for_update(task_id)
        if task.status != PlacementTask.Status.IN_PROGRESS:
            raise PlacementExecutionError("Отметить проблему можно только для задачи IN_PROGRESS.")
        if task.assigned_to_id and task.assigned_to_id != user.pk:
            raise PlacementExecutionError("Задача назначена другому сотруднику.")
        task.status = PlacementTask.Status.FAILED
        task.completed_at = timezone.now()
        if reason:
            task.save(update_fields=["status", "completed_at"])
        else:
            task.save(update_fields=["status", "completed_at"])
    broadcast_task_pool("placement_task.updated", {"id": task.pk, "status": task.status})
    return task
