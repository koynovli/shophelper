from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Equipment, EquipmentSlot, Inventory, Planogram, ProductBatch, StockItem
from .placement_sync import reconcile_for_product, reconcile_planogram


@receiver(post_save, sender=Planogram)
def planogram_saved(sender, instance: Planogram, **kwargs):
    reconcile_planogram(instance)


@receiver(post_delete, sender=Planogram)
def planogram_deleted(sender, instance: Planogram, **kwargs):
    from .models import PlacementTask

    PlacementTask.objects.filter(planogram_id=instance.pk, status=PlacementTask.Status.PENDING).delete()


@receiver(post_save, sender=StockItem)
def stock_item_saved(sender, instance: StockItem, **kwargs):
    reconcile_for_product(instance.product_id)


@receiver(post_save, sender=Inventory)
def inventory_saved(sender, instance: Inventory, **kwargs):
    reconcile_for_product(instance.product_id)


@receiver(post_delete, sender=Inventory)
def inventory_deleted(sender, instance: Inventory, **kwargs):
    reconcile_for_product(instance.product_id)


@receiver(post_save, sender=ProductBatch)
def product_batch_created(sender, instance: ProductBatch, created: bool, **kwargs):
    if not created:
        return
    stock, _ = StockItem.objects.get_or_create(product=instance.product, defaults={"quantity": 0})
    stock.quantity = int(stock.quantity) + int(instance.current_quantity)
    stock.save(update_fields=["quantity"])


def _generate_default_slots_for_equipment(equipment: Equipment) -> None:
    if EquipmentSlot.objects.filter(equipment=equipment).exists():
        return

    eq_type = str(equipment.type)
    rows = int(equipment.rows_count or 0)

    if eq_type in (Equipment.EquipmentType.SHELVING, Equipment.EquipmentType.FRIDGE, "shelf"):
        rows = max(rows, 1)
        for r in range(rows):
            for c in range(4):
                EquipmentSlot.objects.create(
                    equipment=equipment,
                    row_index=r,
                    col_index=c,
                    width_percent=25.0,
                )
        return

    if eq_type == Equipment.EquipmentType.PALLET:
        EquipmentSlot.objects.create(
            equipment=equipment,
            row_index=0,
            col_index=0,
            width_percent=100.0,
        )
        return

    if eq_type == Equipment.EquipmentType.PEGBOARD:
        rows = max(rows, 1)
        for r in range(rows):
            for c in range(5):
                EquipmentSlot.objects.create(
                    equipment=equipment,
                    row_index=r,
                    col_index=c,
                    width_percent=20.0,
                )
        return

    # display/прочее: как базовый вариант — 1x4
    for c in range(4):
        EquipmentSlot.objects.create(
            equipment=equipment,
            row_index=0,
            col_index=c,
            width_percent=25.0,
        )


@receiver(post_save, sender=Equipment)
def equipment_created(sender, instance: Equipment, created: bool, **kwargs):
    if not created:
        return
    _generate_default_slots_for_equipment(instance)
