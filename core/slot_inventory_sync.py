from __future__ import annotations

from django.db.models import Q, Sum

from .models import EquipmentSlot, Inventory, Planogram, Shelf
from .placement_sync import reconcile_slot
from .spatial_engine import resolve_shelf_for_slot


def slots_for_shelf_product(shelf: Shelf, product_id: int):
    """Слоты планограммы для полки и товара."""
    return EquipmentSlot.objects.filter(
        Q(shelf_id=shelf.pk)
        | Q(equipment_id=shelf.equipment_id, row_index=max(0, shelf.level - 1)),
        planograms__product_id=product_id,
    ).distinct()


def sync_slot_qty_from_inventory(inventory: Inventory) -> None:
    """Агрегирует Inventory SHELF на полке → EquipmentSlot.current_qty."""
    if inventory.status != Inventory.LocationStatus.SHELF or not inventory.shelf_id:
        return
    shelf = inventory.shelf
    total = int(
        Inventory.objects.filter(
            store_id=inventory.store_id,
            product_id=inventory.product_id,
            shelf_id=shelf.pk,
            status=Inventory.LocationStatus.SHELF,
        ).aggregate(s=Sum("quantity"))["s"]
        or 0
    )
    for slot in slots_for_shelf_product(shelf, inventory.product_id):
        EquipmentSlot.objects.filter(pk=slot.pk).update(current_qty=total)
        reconcile_slot(EquipmentSlot.objects.get(pk=slot.pk))


def sync_inventory_from_slot(slot: EquipmentSlot, product_id: int, store_id: int) -> None:
    """Поддержка product-tracking: одна строка SHELF на полку+товар = current_qty слота."""
    shelf = resolve_shelf_for_slot(slot)
    if shelf is None:
        return
    inv, _ = Inventory.objects.get_or_create(
        store_id=store_id,
        product_id=product_id,
        shelf_id=shelf.pk,
        status=Inventory.LocationStatus.SHELF,
        defaults={"quantity": 0},
    )
    if int(inv.quantity) != int(slot.current_qty):
        inv.quantity = int(slot.current_qty)
        inv.save(update_fields=["quantity"])


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
