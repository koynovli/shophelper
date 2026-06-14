"""Пересборка слотов и полок при изменении type / rows_count оборудования."""

from __future__ import annotations

from django.db import transaction

from .equipment_profiles import (
    default_slots_spec,
    get_profile,
    needs_shelves,
    shelf_dimensions_for_equipment,
)
from .models import Equipment, EquipmentSlot, Inventory, Planogram, PlacementTask, Shelf
from .slot_inventory_sync import link_slots_to_shelf


LAYOUT_CHANGE_BLOCKED_MSG = (
    "Нельзя изменить тип/ряды: на оборудовании есть товар или активная задача выкладки."
)

_UNSET = object()


def equipment_has_blocking_stock_or_tasks(equipment: Equipment) -> bool:
    if EquipmentSlot.objects.filter(equipment=equipment, current_qty__gt=0).exists():
        return True

    if Inventory.objects.filter(
        shelf__equipment=equipment,
        status=Inventory.LocationStatus.SHELF,
        quantity__gt=0,
    ).exists():
        return True

    return PlacementTask.objects.filter(
        equipment=equipment,
        status__in=(PlacementTask.Status.CREATED, PlacementTask.Status.PENDING),
    ).exists()


def _shelf_row_count(equipment: Equipment) -> int:
    profile = get_profile(equipment.type)
    profile_rows = max(int(equipment.rows_count or 0), 1)
    if profile.layout_mode == "linear":
        return min(profile_rows, profile.max_hanger_rows)
    if profile.layout_mode == "single":
        return 1
    return profile_rows


def resync_equipment_slots(equipment: Equipment) -> None:
    specs = default_slots_spec(equipment)
    target_by_key = {(spec.row_index, spec.col_index): spec for spec in specs}
    target_keys = set(target_by_key.keys())

    planogram_slot_ids = set(
        Planogram.objects.filter(slot__equipment=equipment).values_list("slot_id", flat=True)
    )

    for slot in EquipmentSlot.objects.filter(equipment=equipment):
        key = (slot.row_index, slot.col_index)
        if key in target_keys:
            spec = target_by_key[key]
            EquipmentSlot.objects.filter(pk=slot.pk).update(
                width_percent=spec.width_percent,
                slot_label=spec.slot_label,
            )
        elif slot.pk in planogram_slot_ids:
            continue
        else:
            slot.delete()

    existing_keys = set(
        EquipmentSlot.objects.filter(equipment=equipment).values_list(
            "row_index", "col_index"
        )
    )
    for key, spec in target_by_key.items():
        if key in existing_keys:
            continue
        EquipmentSlot.objects.create(
            equipment=equipment,
            row_index=spec.row_index,
            col_index=spec.col_index,
            width_percent=spec.width_percent,
            slot_label=spec.slot_label,
        )


def resync_equipment_shelves(equipment: Equipment) -> None:
    if not needs_shelves(equipment.type):
        Shelf.objects.filter(equipment=equipment).delete()
        return

    row_count = _shelf_row_count(equipment)
    for level in range(1, row_count + 1):
        dims = shelf_dimensions_for_equipment(equipment, level)
        shelf, created = Shelf.objects.get_or_create(
            equipment=equipment,
            level=level,
            defaults={
                "width": dims["width"],
                "height": dims["height"],
                "depth": dims["depth"],
            },
        )
        if not created:
            shelf.width = dims["width"]
            shelf.height = dims["height"]
            shelf.depth = dims["depth"]
            shelf.save(update_fields=["width", "height", "depth"])

    for shelf in Shelf.objects.filter(equipment=equipment, level__gt=row_count):
        has_inventory = Inventory.objects.filter(
            shelf=shelf,
            status=Inventory.LocationStatus.SHELF,
            quantity__gt=0,
        ).exists()
        if not has_inventory:
            shelf.delete()

    for shelf in Shelf.objects.filter(equipment=equipment):
        link_slots_to_shelf(shelf)


def _refresh_planogram_capacities(equipment: Equipment) -> None:
    from .spatial_engine import refresh_slot_max_capacity

    for slot in EquipmentSlot.objects.filter(equipment=equipment).prefetch_related(
        "planograms__product"
    ):
        for planogram in slot.planograms.all():
            refresh_slot_max_capacity(slot, planogram.product)


@transaction.atomic
def resync_equipment_layout(equipment: Equipment) -> None:
    equipment = Equipment.objects.select_for_update().get(pk=equipment.pk)
    resync_equipment_slots(equipment)
    resync_equipment_shelves(equipment)
    _refresh_planogram_capacities(equipment)


def layout_fields_changed(
    equipment: Equipment,
    *,
    new_type: str | None = None,
    new_rows_count: int | None = None,
    new_row_slot_layouts: object = _UNSET,
) -> bool:
    if new_type is not None and str(new_type) != str(equipment.type):
        return True
    if new_rows_count is not None and int(new_rows_count) != int(equipment.rows_count or 0):
        return True
    if new_row_slot_layouts is not _UNSET and (
        new_row_slot_layouts or []
    ) != (equipment.row_slot_layouts or []):
        return True
    return False
