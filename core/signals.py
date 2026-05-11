from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Inventory, Planogram, StockItem
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
