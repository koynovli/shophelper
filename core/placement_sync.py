from __future__ import annotations

from django.db.models import Sum

from .models import Inventory, PlacementTask, Planogram, StockItem


def _quantity_on_shelf_for_equipment(*, equipment_id: int, product_id: int) -> int:
    total = (
        Inventory.objects.filter(
            product_id=product_id,
            shelf__equipment_id=equipment_id,
            status=Inventory.LocationStatus.SHELF,
        ).aggregate(t=Sum("quantity"))["t"]
    )
    return int(total or 0)


def reconcile_planogram(planogram: Planogram) -> None:
    """
    Создаёт/обновляет одну PENDING-задачу на выкладку по планограмме и складу.

    Количество задачи = min(остаток на складе, нехватка до целевого количества на полке).
    """
    stock = StockItem.objects.filter(product_id=planogram.product_id).first()
    stock_qty = int(stock.quantity) if stock else 0

    equipment_id = planogram.slot.equipment_id
    on_shelf = _quantity_on_shelf_for_equipment(
        equipment_id=equipment_id,
        product_id=planogram.product_id,
    )
    needed = max(0, int(planogram.target_quantity) - on_shelf)

    pending_qs = PlacementTask.objects.filter(
        planogram=planogram,
        status=PlacementTask.Status.PENDING,
    )

    if needed <= 0 or stock_qty <= 0:
        pending_qs.delete()
        return

    task_qty = min(needed, stock_qty)
    PlacementTask.objects.update_or_create(
        planogram=planogram,
        status=PlacementTask.Status.PENDING,
        defaults={
            "product_id": planogram.product_id,
            "equipment_id": equipment_id,
            "quantity": task_qty,
        },
    )


def reconcile_for_product(product_id: int) -> None:
    for pg in Planogram.objects.filter(product_id=product_id).select_related(
        "slot",
        "slot__equipment",
        "product",
    ):
        reconcile_planogram(pg)


