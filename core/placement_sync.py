from __future__ import annotations

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import PlacementTask, Planogram, ProductBatch, StockItem


def _reserve_from_batches(product_id: int, requested_qty: int) -> int:
    """
    FEFO-резерв из партий: сначала ближайший срок годности.

    Возвращает фактически зарезервированное количество.
    """
    if requested_qty <= 0:
        return 0

    today = timezone.localdate()
    remaining = requested_qty
    reserved = 0
    batches = ProductBatch.objects.select_for_update().filter(
        product_id=product_id,
        is_active=True,
        current_quantity__gt=0,
        expiration_date__gte=today,
    ).order_by("expiration_date", "pk")

    for batch in batches:
        if remaining <= 0:
            break
        take = min(int(batch.current_quantity), remaining)
        if take <= 0:
            continue
        batch.current_quantity = int(batch.current_quantity) - take
        if batch.current_quantity == 0:
            batch.is_active = False
        batch.save(update_fields=["current_quantity", "is_active"])
        remaining -= take
        reserved += take

    return reserved


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
        batch_available = (
            ProductBatch.objects.filter(
                product_id=pg.product_id,
                is_active=True,
                current_quantity__gt=0,
                expiration_date__gte=timezone.localdate(),
            ).aggregate(total=Sum("current_quantity"))["total"]
            or 0
        )
        effective_stock_qty = min(stock_qty, int(batch_available)) if int(batch_available) > 0 else stock_qty
        task_qty = min(deficit, effective_stock_qty)
        if task_qty <= 0:
            return

        reserved_from_batches = _reserve_from_batches(pg.product_id, task_qty)
        if int(batch_available) > 0:
            task_qty = min(task_qty, reserved_from_batches)
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


