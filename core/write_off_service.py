from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .media_upload import save_task_photo
from .models import (
    EquipmentSlot,
    Inventory,
    PlacementTask,
    Planogram,
    ProductBatch,
    ShelfWriteOff,
    WarehouseWriteOff,
    WriteOffTask,
    User,
)
from .placement_sync import reconcile_slot, sync_stock_item_from_batches
from .slot_inventory_sync import sync_inventory_from_slot
from .ws_broadcast import broadcast_task_pool

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


class WriteOffError(ValidationError):
    pass


ACTIVE_WRITE_OFF_STATUSES = (
    WriteOffTask.Status.CREATED,
    WriteOffTask.Status.PENDING,
    WriteOffTask.Status.IN_PROGRESS,
)

ACTIVE_PLACEMENT_STATUSES = (
    PlacementTask.Status.CREATED,
    PlacementTask.Status.PENDING,
    PlacementTask.Status.IN_PROGRESS,
)


@dataclass
class WriteOffScanEntry:
    location: str
    product_id: int
    batch_id: int | None
    quantity: int
    slot_id: int | None = None
    planogram_id: int | None = None


@dataclass
class WriteOffScanResult:
    dry_run: bool = False
    warehouse_tasks: int = 0
    shelf_tasks: int = 0
    warehouse_units: int = 0
    shelf_units: int = 0
    entries: list[WriteOffScanEntry] = field(default_factory=list)
    created_task_ids: list[int] = field(default_factory=list)

    @property
    def tasks_total(self) -> int:
        return self.warehouse_tasks + self.shelf_tasks

    def to_dict(self) -> dict:
        return {
            "dry_run": self.dry_run,
            "warehouse_tasks": self.warehouse_tasks,
            "shelf_tasks": self.shelf_tasks,
            "tasks_total": self.tasks_total,
            "warehouse_units": self.warehouse_units,
            "shelf_units": self.shelf_units,
            "units_total": self.warehouse_units + self.shelf_units,
            "created_task_ids": self.created_task_ids,
            "entries": [
                {
                    "location": e.location,
                    "product_id": e.product_id,
                    "batch_id": e.batch_id,
                    "quantity": e.quantity,
                    "slot_id": e.slot_id,
                    "planogram_id": e.planogram_id,
                }
                for e in self.entries
            ],
        }


def _last_completed_placement(planogram_id: int) -> PlacementTask | None:
    return (
        PlacementTask.objects.filter(
            planogram_id=planogram_id,
            status=PlacementTask.Status.COMPLETED,
            batch_id__isnull=False,
        )
        .select_related("batch")
        .order_by("-completed_at", "-pk")
        .first()
    )


def _has_open_warehouse_task(batch_id: int) -> bool:
    return WriteOffTask.objects.filter(
        batch_id=batch_id,
        location=WriteOffTask.Location.WAREHOUSE,
        status__in=ACTIVE_WRITE_OFF_STATUSES,
    ).exists()


def _has_open_shelf_task(batch_id: int, slot_id: int) -> bool:
    return WriteOffTask.objects.filter(
        batch_id=batch_id,
        slot_id=slot_id,
        location=WriteOffTask.Location.SHELF,
        status__in=ACTIVE_WRITE_OFF_STATUSES,
    ).exists()


def _iter_expired_warehouse_batches(store_id: int | None):
    today = timezone.localdate()
    qs = ProductBatch.objects.filter(
        expiration_date__lt=today,
        is_active=True,
        current_quantity__gt=0,
    ).select_related("product", "store")
    if store_id is not None:
        qs = qs.filter(store_id=store_id)
    yield from qs.order_by("expiration_date", "pk")


def _iter_expired_shelf_candidates(store_id: int | None):
    pg_qs = (
        Planogram.objects.filter(slot__current_qty__gt=0)
        .select_related(
            "slot",
            "slot__equipment",
            "slot__equipment__zone",
            "product",
        )
        .order_by("pk")
    )
    if store_id is not None:
        pg_qs = pg_qs.filter(slot__equipment__zone__store_id=store_id)

    for pg in pg_qs:
        task = _last_completed_placement(pg.pk)
        if task is None or task.batch_id is None:
            continue
        batch = task.batch
        if not batch.is_expired:
            continue
        qty = int(pg.slot.current_qty or 0)
        if qty <= 0:
            continue
        yield pg, batch, task, qty


def scan_expired_write_off_tasks(
    store_id: int | None = None,
    *,
    dry_run: bool = False,
) -> WriteOffScanResult:
    """Находит просрочку на складе и полках; создаёт WriteOffTask (или preview)."""
    result = WriteOffScanResult(dry_run=dry_run)

    for batch in _iter_expired_warehouse_batches(store_id):
        qty = int(batch.current_quantity)
        if _has_open_warehouse_task(batch.pk):
            continue
        result.entries.append(
            WriteOffScanEntry(
                location=WriteOffTask.Location.WAREHOUSE,
                product_id=batch.product_id,
                batch_id=batch.pk,
                quantity=qty,
            )
        )
        result.warehouse_tasks += 1
        result.warehouse_units += qty

        if dry_run:
            continue

        task = WriteOffTask.objects.create(
            store_id=batch.store_id,
            product_id=batch.product_id,
            batch_id=batch.pk,
            quantity=qty,
            location=WriteOffTask.Location.WAREHOUSE,
            trigger=WriteOffTask.Trigger.EXPIRED_AUTO,
            status=WriteOffTask.Status.CREATED,
        )
        result.created_task_ids.append(task.pk)
        _broadcast_created(task)

    for pg, batch, placement_task, qty in _iter_expired_shelf_candidates(store_id):
        if _has_open_shelf_task(batch.pk, pg.slot_id):
            continue
        result.entries.append(
            WriteOffScanEntry(
                location=WriteOffTask.Location.SHELF,
                product_id=pg.product_id,
                batch_id=batch.pk,
                quantity=qty,
                slot_id=pg.slot_id,
                planogram_id=pg.pk,
            )
        )
        result.shelf_tasks += 1
        result.shelf_units += qty

        if dry_run:
            continue

        task = WriteOffTask.objects.create(
            store_id=pg.slot.equipment.zone.store_id,
            product_id=pg.product_id,
            batch_id=batch.pk,
            quantity=qty,
            location=WriteOffTask.Location.SHELF,
            trigger=WriteOffTask.Trigger.EXPIRED_AUTO,
            slot_id=pg.slot_id,
            planogram_id=pg.pk,
            equipment_id=pg.slot.equipment_id,
            placement_task_id=placement_task.pk,
            status=WriteOffTask.Status.CREATED,
        )
        result.created_task_ids.append(task.pk)
        _broadcast_created(task)

    return result


def create_manual_warehouse_write_off_task(
    manager: AbstractUser,
    *,
    batch_id: int,
    quantity: int,
    reason: str = "",
) -> WriteOffTask:
    if getattr(manager, "role", None) != User.Role.ADMIN:
        raise WriteOffError("Создавать задания на списание может только менеджер.")

    reason = (reason or "").strip()
    if quantity < 1:
        raise WriteOffError("Количество должно быть не меньше 1.")

    with transaction.atomic():
        batch = ProductBatch.objects.select_for_update().select_related("product", "store").get(
            pk=batch_id
        )
        if quantity > int(batch.current_quantity):
            raise WriteOffError(
                f"Нельзя списать {quantity} шт.: в партии только {batch.current_quantity}."
            )
        if _has_open_warehouse_task(batch.pk):
            raise WriteOffError("По этой партии уже есть активное задание на списание.")

        task = WriteOffTask.objects.create(
            store_id=batch.store_id,
            product_id=batch.product_id,
            batch_id=batch.pk,
            quantity=quantity,
            location=WriteOffTask.Location.WAREHOUSE,
            trigger=WriteOffTask.Trigger.MANUAL,
            reason=reason,
            created_by=manager,
            status=WriteOffTask.Status.CREATED,
        )

    _broadcast_created(task)
    return task


def accept_write_off_task(task_id: int, user: AbstractUser) -> WriteOffTask:
    with transaction.atomic():
        task = WriteOffTask.objects.select_for_update().get(pk=task_id)
        if task.status not in (WriteOffTask.Status.CREATED, WriteOffTask.Status.PENDING):
            raise WriteOffError("Задание можно взять только в статусе CREATED.")
        if task.assigned_to_id and task.assigned_to_id != user.pk:
            raise WriteOffError("Задание назначено другому сотруднику.")
        task.assigned_to = user
        task.status = WriteOffTask.Status.IN_PROGRESS
        task.save(update_fields=["assigned_to", "status"])

    broadcast_task_pool(
        "write_off_task.updated",
        {"id": str(task.pk), "status": task.status},
    )
    return task


def _purge_depleted_batch(batch: ProductBatch, task: WriteOffTask | None = None) -> None:
    """Удаляет партию из БД после полного списания со склада."""
    if int(batch.current_quantity) == 0:
        Inventory.objects.filter(batch_id=batch.pk).delete()
        batch.delete()
        if task is not None and task.batch_id:
            task.batch_id = None
            task._state.fields_cache.pop("batch", None)


def _execute_warehouse_write_off(task: WriteOffTask) -> int:
    if task.batch_id is None:
        raise WriteOffError("Для списания со склада нужна партия.")
    batch = ProductBatch.objects.select_for_update().get(pk=task.batch_id)
    write_qty = min(int(task.quantity), int(batch.current_quantity))
    if write_qty <= 0:
        raise WriteOffError("В партии не осталось товара для списания.")
    batch.deduct_quantity(write_qty)
    sync_stock_item_from_batches(task.product_id)
    wh_reason = (
        WarehouseWriteOff.Reason.MANUAL
        if task.trigger == WriteOffTask.Trigger.MANUAL
        else WarehouseWriteOff.Reason.EXPIRED_BATCH
    )
    WarehouseWriteOff.objects.create(
        store_id=task.store_id,
        product_id=task.product_id,
        batch_id=task.batch_id,
        write_off_task=task,
        quantity=write_qty,
        reason=wh_reason,
    )
    _purge_depleted_batch(batch, task)
    return write_qty


def _execute_shelf_write_off(task: WriteOffTask) -> int:
    if task.slot_id is None:
        raise WriteOffError("Для списания с полки нужен слот.")
    slot = EquipmentSlot.objects.select_for_update().get(pk=task.slot_id)
    on_shelf = int(slot.current_qty or 0)
    if on_shelf <= 0:
        raise WriteOffError("На полке уже нет товара.")
    write_qty = min(int(task.quantity), on_shelf)
    slot.current_qty = max(0, on_shelf - write_qty)
    slot.save(update_fields=["current_qty"])
    sync_inventory_from_slot(slot, task.product_id, task.store_id)

    shelf_reason = (
        ShelfWriteOff.Reason.MANUAL
        if task.trigger == WriteOffTask.Trigger.MANUAL
        else ShelfWriteOff.Reason.EXPIRED_PLACEMENT_BATCH
    )
    ShelfWriteOff.objects.create(
        store_id=task.store_id,
        slot=slot,
        product_id=task.product_id,
        batch_id=task.batch_id,
        planogram_id=task.planogram_id,
        placement_task_id=task.placement_task_id,
        quantity=write_qty,
        reason=shelf_reason,
        write_off_task=task,
    )

    if task.planogram_id:
        PlacementTask.objects.filter(
            planogram_id=task.planogram_id,
            status__in=ACTIVE_PLACEMENT_STATUSES,
        ).update(status=PlacementTask.Status.CANCELLED)

    reconcile_slot(EquipmentSlot.objects.get(pk=slot.pk))
    return write_qty


def complete_write_off_task(
    task_id: int,
    user: AbstractUser,
    photo_file=None,
    *,
    raw_code: str | None = None,
    store_id: int | None = None,
) -> WriteOffTask:
    with transaction.atomic():
        task = WriteOffTask.objects.select_for_update().select_related(
            "product", "slot"
        ).get(pk=task_id)
        if task.status != WriteOffTask.Status.IN_PROGRESS:
            raise WriteOffError("Завершить можно только задание IN_PROGRESS.")
        if task.assigned_to_id and task.assigned_to_id != user.pk:
            raise WriteOffError("Задание назначено другому сотруднику.")

        from .scan_service import validate_task_product_scan

        try:
            validate_task_product_scan(
                task_product_id=task.product_id,
                raw_code=raw_code or "",
                store_id=store_id or task.store_id,
                expected_batch_id=task.batch_id,
            )
        except ValueError as exc:
            raise WriteOffError(str(exc)) from exc

        if task.location == WriteOffTask.Location.WAREHOUSE:
            write_qty = _execute_warehouse_write_off(task)
        else:
            write_qty = _execute_shelf_write_off(task)

        update_fields = ["status", "completed_at", "quantity"]
        task.quantity = write_qty
        if photo_file is not None:
            task.photo_url = save_task_photo(photo_file, prefix="writeoff_reports")
            update_fields.append("photo_url")
        if task.batch_id is None:
            update_fields.append("batch")
        task.status = WriteOffTask.Status.COMPLETED
        task.completed_at = timezone.now()
        task.save(update_fields=update_fields)

    broadcast_task_pool(
        "write_off_task.completed",
        {"id": str(task.pk), "status": task.status},
    )
    return task


def cancel_write_off_task(task_id: int, manager: AbstractUser) -> WriteOffTask:
    if getattr(manager, "role", None) != User.Role.ADMIN:
        raise WriteOffError("Отменять задания может только менеджер.")
    with transaction.atomic():
        task = WriteOffTask.objects.select_for_update().get(pk=task_id)
        if task.status in (WriteOffTask.Status.COMPLETED, WriteOffTask.Status.CANCELLED):
            raise WriteOffError("Задание уже закрыто.")
        task.status = WriteOffTask.Status.CANCELLED
        task.save(update_fields=["status"])

    broadcast_task_pool(
        "write_off_task.updated",
        {"id": str(task.pk), "status": task.status},
    )
    return task


def _broadcast_created(task: WriteOffTask) -> None:
    task = WriteOffTask.objects.select_related("product", "equipment").get(pk=task.pk)
    loc = "склад" if task.location == WriteOffTask.Location.WAREHOUSE else "полка"
    broadcast_task_pool(
        "write_off_task.created",
        {
            "id": str(task.pk),
            "product_name": task.product.name,
            "quantity": task.quantity,
            "location": loc,
        },
    )
