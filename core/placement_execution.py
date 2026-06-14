from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .media_upload import save_task_photo
from .models import EquipmentSlot, PlacementTask
from .placement_sync import (
    available_batch_qty,
    deduct_from_batches,
    reconcile_planogram,
)
from .slot_inventory_sync import sync_inventory_from_slot
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


def _ensure_batch_availability(product_id: int, qty: int) -> None:
    avail = available_batch_qty(product_id)
    if avail < qty:
        raise PlacementExecutionError(
            f"На складе недостаточно годных партий (доступно {avail} из {qty}). "
            "Проверьте приёмку или срок годности партий."
        )


def accept_placement_task(task_id: int, user: AbstractUser) -> PlacementTask:
    with transaction.atomic():
        task = _get_task_for_update(task_id)
        if task.status not in (PlacementTask.Status.CREATED, PlacementTask.Status.PENDING):
            raise PlacementExecutionError("Задачу можно взять только в статусе CREATED.")
        if task.assigned_to_id and task.assigned_to_id != user.pk:
            raise PlacementExecutionError("Задача уже назначена другому сотруднику.")
        _ensure_batch_availability(task.product_id, int(task.quantity))
        task.assigned_to = user
        task.status = PlacementTask.Status.IN_PROGRESS
        task.save(update_fields=["assigned_to", "status"])
    broadcast_task_pool("placement_task.updated", {"id": task.pk, "status": task.status})
    return task


def verify_slot(task_id: int, user: AbstractUser, scanned_qr_token: uuid.UUID) -> PlacementTask:
    with transaction.atomic():
        task = _get_task_for_update(task_id)
        if task.status != PlacementTask.Status.IN_PROGRESS:
            raise PlacementExecutionError("QR можно сканировать только для задачи IN_PROGRESS.")
        if task.assigned_to_id and task.assigned_to_id != user.pk:
            raise PlacementExecutionError("Задача назначена другому сотруднику.")
        if task.planogram_id is None or task.planogram.slot_id is None:
            raise PlacementExecutionError("У задачи нет привязки к слоту.")
        slot = task.planogram.slot
        if slot.qr_token != scanned_qr_token:
            raise PlacementExecutionError("QR-код не совпадает с целевым слотом.")
        if task.slot_verified_at is None:
            task.slot_verified_at = timezone.now()
            task.save(update_fields=["slot_verified_at"])
    broadcast_task_pool("placement_task.updated", {"id": task.pk, "slot_verified": True})
    return task


def complete_placement_task(task_id: int, user: AbstractUser, photo_file) -> PlacementTask:
    with transaction.atomic():
        task = _get_task_for_update(task_id)
        if task.status != PlacementTask.Status.IN_PROGRESS:
            raise PlacementExecutionError("Завершить можно только задачу IN_PROGRESS.")
        if task.assigned_to_id and task.assigned_to_id != user.pk:
            raise PlacementExecutionError("Задача назначена другому сотруднику.")

        qty = int(task.quantity)
        _ensure_batch_availability(task.product_id, qty)
        deducted, batch_id = deduct_from_batches(task.product_id, qty)
        if deducted < qty:
            raise PlacementExecutionError(
                f"На складе недостаточно годных партий (доступно {deducted} из {qty}). "
                "Проверьте приёмку или срок годности партий."
            )

        slot = EquipmentSlot.objects.select_for_update().get(pk=task.planogram.slot_id)
        slot.current_qty = int(slot.current_qty) + qty
        slot.save(update_fields=["current_qty"])
        store_id = task.equipment.zone.store_id
        sync_inventory_from_slot(slot, task.product_id, store_id)

        update_fields = ["batch", "status", "completed_at"]
        if photo_file is not None:
            task.photo_url = save_task_photo(photo_file, prefix="placement_reports")
            update_fields.append("photo_url")
        task.batch_id = batch_id or task.batch_id
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
