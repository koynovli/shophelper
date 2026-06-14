from __future__ import annotations

from dataclasses import dataclass, field

from django.utils import timezone

from .models import Planogram, PlacementTask, ProductBatch
from .write_off_service import scan_expired_write_off_tasks


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
    Устаревший мгновенный списание с полок.
    Используйте scan_expired_write_off_tasks + complete_write_off_task.
    """
    scan = scan_expired_write_off_tasks(store_id, dry_run=True)
    result = WriteOffResult(dry_run=dry_run)
    for entry in scan.entries:
        if entry.location != "SHELF":
            continue
        result.entries.append(
            WriteOffEntry(
                planogram_id=entry.planogram_id or 0,
                slot_id=entry.slot_id or 0,
                product_id=entry.product_id,
                batch_id=entry.batch_id,
                quantity=entry.quantity,
                placement_task_id=None,
            )
        )
        result.slots_written_off += 1
        result.units_written_off += entry.quantity

    if dry_run:
        return result

    created = scan_expired_write_off_tasks(store_id, dry_run=False)
    result.slots_written_off = created.shelf_tasks
    result.units_written_off = created.shelf_units
    _deactivate_empty_expired_batches(store_id)
    return result
