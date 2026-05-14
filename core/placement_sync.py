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


def release_placement_task_reservation(product_id: int, qty: int) -> None:
    """
    Возвращает резерв задачи на выкладку: увеличивает StockItem и зачисляет
    количество в партию с ближайшим сроком годности (приближение к обратному FEFO).
    """
    if qty <= 0:
        return
    stock = StockItem.objects.select_for_update().filter(product_id=product_id).first()
    if stock is None:
        StockItem.objects.create(product_id=product_id, quantity=qty)
    else:
        stock.quantity = int(stock.quantity) + qty
        stock.save(update_fields=["quantity"])

    batch = (
        ProductBatch.objects.select_for_update()
        .filter(product_id=product_id)
        .order_by("expiration_date", "pk")
        .first()
    )
    if batch is not None:
        batch.current_quantity = int(batch.current_quantity) + qty
        batch.is_active = True
        batch.save(update_fields=["current_quantity", "is_active"])


def reconcile_planogram(planogram: Planogram) -> None:
    """
    Резервирует склад под дефицит планограммы (цель минус уже выложенное минус «в пути»).

    Уже выполненные задачи (COMPLETED) считаются товаром на витрине по этой планограмме.
    PENDING и IN_PROGRESS — зарезервировано со склада, но ещё не отмечено как выложенное.
    """
    with transaction.atomic():
        pg = (
            Planogram.objects.select_for_update()
            .select_related("slot", "slot__equipment", "product")
            .get(pk=planogram.pk)
        )

        completed_sum = (
            PlacementTask.objects.filter(
                planogram_id=pg.pk,
                status=PlacementTask.Status.COMPLETED,
            ).aggregate(total=Sum("quantity"))["total"]
        )
        completed_qty = int(completed_sum or 0)

        open_qs = PlacementTask.objects.select_for_update().filter(
            planogram_id=pg.pk,
            status__in=(
                PlacementTask.Status.PENDING,
                PlacementTask.Status.IN_PROGRESS,
            ),
        )
        reserved_qty = int(open_qs.aggregate(total=Sum("quantity"))["total"] or 0)

        deficit = int(pg.target_quantity) - completed_qty - reserved_qty
        if deficit <= 0:
            return

        stock = (
            StockItem.objects.select_for_update()
            .filter(product_id=pg.product_id)
            .first()
        )
        if stock is None or int(stock.quantity) <= 0:
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
        add_qty = min(deficit, effective_stock_qty)
        if add_qty <= 0:
            return

        reserved_from_batches = _reserve_from_batches(pg.product_id, add_qty)
        if int(batch_available) > 0:
            add_qty = min(add_qty, reserved_from_batches)
            if add_qty <= 0:
                return

        existing = open_qs.filter(status=PlacementTask.Status.PENDING).first()
        if existing is None:
            existing = open_qs.filter(status=PlacementTask.Status.IN_PROGRESS).first()
        if existing is not None:
            existing.quantity = int(existing.quantity) + add_qty
            existing.save(update_fields=["quantity"])
        else:
            PlacementTask.objects.create(
                planogram_id=pg.pk,
                product_id=pg.product_id,
                equipment_id=pg.slot.equipment_id,
                quantity=add_qty,
                status=PlacementTask.Status.PENDING,
            )
        stock.quantity = stock_qty - add_qty
        stock.save(update_fields=["quantity"])


def reconcile_for_product(product_id: int) -> None:
    for pg in Planogram.objects.filter(product_id=product_id).select_related(
        "slot",
        "slot__equipment",
        "product",
    ):
        reconcile_planogram(pg)


