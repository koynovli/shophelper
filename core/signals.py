from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .equipment_profiles import (
    default_slots_spec,
    needs_shelves,
    shelf_dimensions_for_equipment,
)
from .models import Equipment, EquipmentSlot, Inventory, Planogram, Product, ProductBatch, Shelf, StockItem
from .placement_sync import reconcile_for_product, reconcile_planogram, sync_stock_item_from_batches
from .slot_inventory_sync import (
    is_operational_side_effects_suppressed,
    link_slots_to_shelf,
    sync_slot_qty_from_inventory,
)


def _sync_planogram_slot_capacity(planogram: Planogram) -> None:
    from .product_units import product_stores_weight
    from .spatial_engine import refresh_slot_max_capacity

    cap = refresh_slot_max_capacity(planogram.slot, planogram.product)
    if product_stores_weight(planogram.product):
        if cap > 0 and int(planogram.target_quantity or 0) > cap:
            Planogram.objects.filter(pk=planogram.pk).update(target_quantity=cap)
            planogram.target_quantity = cap
        return
    if int(planogram.target_quantity or 0) < 1 and cap > 0:
        Planogram.objects.filter(pk=planogram.pk).update(target_quantity=cap)
        planogram.target_quantity = cap
    elif cap > 0 and int(planogram.target_quantity) > cap:
        Planogram.objects.filter(pk=planogram.pk).update(target_quantity=cap)
        planogram.target_quantity = cap


@receiver(post_save, sender=Planogram)
def planogram_saved(sender, instance: Planogram, **kwargs):
    _sync_planogram_slot_capacity(instance)
    reconcile_planogram(instance)


@receiver(post_delete, sender=Planogram)
def planogram_deleted(sender, instance: Planogram, **kwargs):
    from .models import PlacementTask
    from .spatial_engine import refresh_slot_max_capacity

    PlacementTask.objects.filter(
        planogram_id=instance.pk,
        status__in=(PlacementTask.Status.CREATED, PlacementTask.Status.PENDING),
    ).delete()

    slot = instance.slot
    if slot is not None:
        refresh_slot_max_capacity(slot)
        EquipmentSlot.objects.filter(pk=slot.pk).update(current_qty=0)


@receiver(post_save, sender=Product)
def product_saved_refresh_slot_capacity(sender, instance: Product, **kwargs):
    from .spatial_engine import refresh_slot_max_capacity

    for planogram in Planogram.objects.filter(product=instance).select_related("slot"):
        refresh_slot_max_capacity(planogram.slot, instance)


@receiver(post_save, sender=StockItem)
def stock_item_saved(sender, instance: StockItem, **kwargs):
    if is_operational_side_effects_suppressed():
        return
    reconcile_for_product(instance.product_id)


@receiver(post_save, sender=Inventory)
def inventory_saved(sender, instance: Inventory, **kwargs):
    if is_operational_side_effects_suppressed():
        return
    sync_slot_qty_from_inventory(instance)
    reconcile_for_product(instance.product_id)


@receiver(post_delete, sender=Inventory)
def inventory_deleted(sender, instance: Inventory, **kwargs):
    if is_operational_side_effects_suppressed():
        return
    sync_slot_qty_from_inventory(instance)
    reconcile_for_product(instance.product_id)


@receiver(post_save, sender=Shelf)
def shelf_saved(sender, instance: Shelf, **kwargs):
    link_slots_to_shelf(instance)


@receiver(post_save, sender=ProductBatch)
def product_batch_saved(sender, instance: ProductBatch, **kwargs):
    sync_stock_item_from_batches(instance.product_id)


def _generate_default_slots_for_equipment(equipment: Equipment) -> None:
    if EquipmentSlot.objects.filter(equipment=equipment).exists():
        return
    for spec in default_slots_spec(equipment):
        EquipmentSlot.objects.create(
            equipment=equipment,
            row_index=spec.row_index,
            col_index=spec.col_index,
            width_percent=spec.width_percent,
            slot_label=spec.slot_label,
        )


def _ensure_default_shelves_for_equipment(equipment: Equipment) -> None:
    if not needs_shelves(equipment.type):
        return
    from .equipment_profiles import get_profile

    profile_rows = max(int(equipment.rows_count or 0), 1)
    profile = get_profile(equipment.type)
    if profile.layout_mode == "linear":
        row_count = min(profile_rows, profile.max_hanger_rows)
    elif profile.layout_mode == "single":
        row_count = 1
    else:
        row_count = profile_rows

    for level in range(1, row_count + 1):
        dims = shelf_dimensions_for_equipment(equipment, level)
        Shelf.objects.get_or_create(
            equipment=equipment,
            level=level,
            defaults={
                "width": dims["width"],
                "height": dims["height"],
                "depth": dims["depth"],
            },
        )


@receiver(post_save, sender=Equipment)
def equipment_created(sender, instance: Equipment, created: bool, **kwargs):
    if not created:
        return
    _generate_default_slots_for_equipment(instance)
    _ensure_default_shelves_for_equipment(instance)
