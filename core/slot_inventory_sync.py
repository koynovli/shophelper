from __future__ import annotations

import contextvars
from contextlib import contextmanager

from django.db.models import Q, Sum
from django.utils import timezone

from .models import EquipmentSlot, Inventory, Planogram, Shelf
from .spatial_engine import resolve_shelf_for_slot

_suppress_operational_side_effects: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "suppress_operational_side_effects",
    default=False,
)


def is_operational_side_effects_suppressed() -> bool:
    return _suppress_operational_side_effects.get()


@contextmanager
def suppress_operational_side_effects():
    """Отключает обратный resync Inventory→Slot и reconcile_for_product в сигналах."""
    token = _suppress_operational_side_effects.set(True)
    try:
        yield
    finally:
        _suppress_operational_side_effects.reset(token)


def slots_for_shelf_product(shelf: Shelf, product_id: int):
    """Слоты планограммы для полки и товара."""
    return EquipmentSlot.objects.filter(
        Q(shelf_id=shelf.pk)
        | Q(equipment_id=shelf.equipment_id, row_index=max(0, shelf.level - 1)),
        planograms__product_id=product_id,
    ).distinct()


def shelf_hall_qty_for_product(shelf: Shelf, product_id: int) -> int:
    """Сумма current_qty по слотам полки с планограммой товара."""
    slot_ids = slots_for_shelf_product(shelf, product_id).values_list("pk", flat=True)
    total = (
        EquipmentSlot.objects.filter(pk__in=slot_ids).aggregate(s=Sum("current_qty"))["s"]
        or 0
    )
    return int(total)


def sync_slot_qty_from_inventory(inventory: Inventory) -> None:
    """Inventory SHELF → EquipmentSlot (только batch-specific строки, не no-batch)."""
    if inventory.status != Inventory.LocationStatus.SHELF or not inventory.shelf_id:
        return
    if inventory.batch_id is None:
        return

    shelf = inventory.shelf
    slot_ids = list(
        slots_for_shelf_product(shelf, inventory.product_id).values_list("pk", flat=True)
    )
    if not slot_ids:
        return

    batch_qty = int(inventory.quantity or 0)
    if len(slot_ids) == 1:
        EquipmentSlot.objects.filter(pk=slot_ids[0]).update(current_qty=batch_qty)
        return

    per_slot = batch_qty // len(slot_ids)
    remainder = batch_qty % len(slot_ids)
    for idx, slot_id in enumerate(slot_ids):
        qty = per_slot + (1 if idx < remainder else 0)
        EquipmentSlot.objects.filter(pk=slot_id).update(current_qty=qty)


def sync_inventory_from_slot(slot: EquipmentSlot, product_id: int, store_id: int) -> None:
    """Slot → Inventory: агрегат по полке, без обратного resync в сигналах."""
    shelf = resolve_shelf_for_slot(slot)
    if shelf is None:
        return
    qty = shelf_hall_qty_for_product(shelf, product_id)

    with suppress_operational_side_effects():
        inv = Inventory.objects.filter(
            store_id=store_id,
            product_id=product_id,
            batch__isnull=True,
        ).first()
        if inv is None:
            Inventory.objects.create(
                store_id=store_id,
                product_id=product_id,
                shelf=shelf,
                status=Inventory.LocationStatus.SHELF,
                quantity=qty,
            )
            return
        Inventory.objects.filter(pk=inv.pk).update(
            shelf_id=shelf.pk,
            status=Inventory.LocationStatus.SHELF,
            quantity=qty,
            updated_at=timezone.now(),
        )


def link_slots_to_shelf(shelf: Shelf) -> None:
    """Привязка EquipmentSlot.shelf и пересчёт max_capacity по планограммам."""
    from .spatial_engine import refresh_slot_max_capacity

    row = max(0, shelf.level - 1)
    slots = EquipmentSlot.objects.filter(
        equipment_id=shelf.equipment_id,
        row_index=row,
    )
    slots.update(shelf_id=shelf.pk)
    for slot in slots.prefetch_related("planograms__product"):
        for pg in slot.planograms.all():
            refresh_slot_max_capacity(slot, pg.product)
