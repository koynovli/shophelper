from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from .models import EquipmentSlot, Planogram, PlacementTask, ProductBatch, ShelfWriteOff
from .placement_sync import reconcile_slot
from .slot_inventory_sync import sync_inventory_from_slot


@dataclass
class WriteOffEntry:
    planogram_id: int
    slot_id: int
    product_id: int
    batch_id: int | None
    quantity: int
    placement_task_id: int | None


@dataclass
class WriteOffResult:
    slots_written_off: int = 0
    units_written_off: int = 0
    entries: list[WriteOffEntry] = field(default_factory=list)
    dry_run: bool = False

    def to_dict(self) -> dict:
        return {
            "dry_run": self.dry_run,
            "slots_written_off": self.slots_written_off,
            "units_written_off": self.units_written_off,
            "entries": [
                {
                    "planogram_id": e.planogram_id,
                    "slot_id": e.slot_id,
                    "product_id": e.product_id,
                    "batch_id": e.batch_id,
                    "quantity": e.quantity,
                    "placement_task_id": e.placement_task_id,
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


def _deactivate_empty_expired_batches(store_id: int | None = None) -> int:
    today = timezone.localdate()
    qs = ProductBatch.objects.filter(
        expiration_date__lt=today,
        is_active=True,
        current_quantity=0,
    )
    if store_id is not None:
        qs = qs.filter(store_id=store_id)
    return qs.update(is_active=False)


def write_off_expired_shelf_stock(
    *,
    store_id: int | None = None,
    dry_run: bool = False,
) -> WriteOffResult:
    """
    Списывает просрочку с полок: если партия последней COMPLETED-выкладки на слот
  просрочена — обнуляет slot.current_qty (склад/партию не трогает).
    """
    result = WriteOffResult(dry_run=dry_run)
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

        qty = int(pg.slot.current_qty)
        if qty <= 0:
            continue

        entry = WriteOffEntry(
            planogram_id=pg.pk,
            slot_id=pg.slot_id,
            product_id=pg.product_id,
            batch_id=batch.pk,
            quantity=qty,
            placement_task_id=task.pk,
        )
        result.entries.append(entry)

        if dry_run:
            result.slots_written_off += 1
            result.units_written_off += qty
            continue

        store_pk = pg.slot.equipment.zone.store_id
        with transaction.atomic():
            slot = EquipmentSlot.objects.select_for_update().get(pk=pg.slot_id)
            if int(slot.current_qty) <= 0:
                continue
            write_qty = int(slot.current_qty)
            slot.current_qty = 0
            slot.save(update_fields=["current_qty"])
            sync_inventory_from_slot(slot, pg.product_id, store_pk)
            ShelfWriteOff.objects.create(
                store_id=store_pk,
                slot=slot,
                product_id=pg.product_id,
                batch=batch,
                planogram=pg,
                placement_task=task,
                quantity=write_qty,
                reason=ShelfWriteOff.Reason.EXPIRED_PLACEMENT_BATCH,
            )
            result.slots_written_off += 1
            result.units_written_off += write_qty

        reconcile_slot(EquipmentSlot.objects.get(pk=pg.slot_id))

    if not dry_run:
        _deactivate_empty_expired_batches(store_id)

    return result
