from __future__ import annotations

from django.db import transaction
from django.db.models import Sum

from .models import PlacementTask, Planogram, StockItem


def reconcile_planogram(planogram: Planogram) -> None:
    """
    Автоматически создаёт новую задачу пополнения и резервирует склад.

    Дефицит считается как target_quantity - сумма PENDING-задач для этой планограммы.
    При создании задачи количество резерва вычитается из StockItem.quantity.
    """
    with transaction.atomic():
        pg = (
            Planogram.objects.select_for_update()
            .select_related("slot", "slot__equipment", "product")
            .get(pk=planogram.pk)
        )
        stock = (
            StockItem.objects.select_for_update()
            .filter(product_id=pg.product_id)
            .first()
        )
        if stock is None or int(stock.quantity) <= 0:
            return

        pending_sum = (
            PlacementTask.objects.filter(
                planogram_id=pg.pk,
                status=PlacementTask.Status.PENDING,
            ).aggregate(total=Sum("quantity"))["total"]
        )
        reserved_qty = int(pending_sum or 0)
        deficit = int(pg.target_quantity) - reserved_qty
        if deficit <= 0:
            return

        stock_qty = int(stock.quantity)
        task_qty = min(deficit, stock_qty)
        if task_qty <= 0:
            return

        PlacementTask.objects.create(
            planogram_id=pg.pk,
            product_id=pg.product_id,
            equipment_id=pg.slot.equipment_id,
            quantity=task_qty,
            status=PlacementTask.Status.PENDING,
        )
        stock.quantity = stock_qty - task_qty
        stock.save(update_fields=["quantity"])


def reconcile_for_product(product_id: int) -> None:
    for pg in Planogram.objects.filter(product_id=product_id).select_related(
        "slot",
        "slot__equipment",
        "product",
    ):
        reconcile_planogram(pg)


