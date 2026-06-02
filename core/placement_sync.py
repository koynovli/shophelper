from __future__ import annotations

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from .models import EquipmentSlot, PlacementTask, Planogram, ProductBatch, StockItem
from .spatial_engine import refresh_slot_max_capacity

DEFICIT_FILL_RATIO = 0.30


def peek_fefo_batch_id(product_id: int) -> int | None:
    """Возвращает id партии FEFO без списания (для привязки к задаче)."""
    today = timezone.localdate()
    batch = (
        ProductBatch.objects.filter(
            product_id=product_id,
            is_active=True,
            current_quantity__gt=0,
            expiration_date__gte=today,
        )
        .order_by("expiration_date", "pk")
        .first()
    )
    return batch.pk if batch else None


def available_batch_qty(product_id: int) -> int:
    today = timezone.localdate()
    total = (
        ProductBatch.objects.filter(
            product_id=product_id,
            is_active=True,
            current_quantity__gt=0,
            expiration_date__gte=today,
        ).aggregate(total=Sum("current_quantity"))["total"]
    )
    return int(total or 0)


def deduct_from_batches(product_id: int, requested_qty: int) -> tuple[int, int | None]:
    """FEFO-списание со склада (партии). Возвращает (списано, id основной партии)."""
    if requested_qty <= 0:
        return 0, None

    today = timezone.localdate()
    remaining = requested_qty
    deducted = 0
    primary_batch_id: int | None = None
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
        if primary_batch_id is None:
            primary_batch_id = batch.pk
        batch.current_quantity = int(batch.current_quantity) - take
        if batch.current_quantity == 0:
            batch.is_active = False
        batch.save(update_fields=["current_quantity", "is_active"])
        remaining -= take
        deducted += take

    if deducted > 0:
        stock = StockItem.objects.select_for_update().filter(product_id=product_id).first()
        if stock is not None:
            stock.quantity = max(0, int(stock.quantity) - deducted)
            stock.save(update_fields=["quantity"])

    return deducted, primary_batch_id


def _in_flight_qty(planogram_id: int) -> int:
    return int(
        PlacementTask.objects.filter(
            planogram_id=planogram_id,
            status__in=(
                PlacementTask.Status.CREATED,
                PlacementTask.Status.PENDING,
                PlacementTask.Status.IN_PROGRESS,
            ),
        ).aggregate(total=Sum("quantity"))["total"]
        or 0
    )


def reconcile_slot(slot: EquipmentSlot) -> None:
    """Проверяет слот по планограмме: триггер 30% и создание задачи CREATED."""
    pg = (
        Planogram.objects.filter(slot_id=slot.pk)
        .select_related("product", "slot", "slot__equipment")
        .first()
    )
    if pg is None:
        return
    reconcile_planogram(pg)


def reconcile_planogram(planogram: Planogram) -> None:
    """
    Проактивный триггер: current_qty < 30% max_capacity → задача CREATED.
    Партия не списывается до COMPLETED (только peek FEFO для batch_id).
    """
    with transaction.atomic():
        pg = (
            Planogram.objects.select_for_update()
            .select_related("slot", "slot__equipment", "product")
            .get(pk=planogram.pk)
        )
        slot = EquipmentSlot.objects.select_for_update().get(pk=pg.slot_id)
        cap = refresh_slot_max_capacity(slot, pg.product)
        if cap <= 0:
            return

        current = int(slot.current_qty)
        if current >= cap * DEFICIT_FILL_RATIO:
            return

        in_flight = _in_flight_qty(pg.pk)
        need_qty = max(0, cap - current - in_flight)
        if need_qty <= 0:
            return

        batch_avail = available_batch_qty(pg.product_id)
        stock = StockItem.objects.filter(product_id=pg.product_id).first()
        stock_qty = int(stock.quantity) if stock else 0
        effective = min(batch_avail, stock_qty) if batch_avail > 0 else stock_qty
        add_qty = min(need_qty, effective)
        if add_qty <= 0:
            return

        primary_batch_id = peek_fefo_batch_id(pg.product_id)

        open_qs = PlacementTask.objects.select_for_update().filter(
            planogram_id=pg.pk,
            status__in=(
                PlacementTask.Status.CREATED,
                PlacementTask.Status.PENDING,
                PlacementTask.Status.IN_PROGRESS,
            ),
        )
        existing = open_qs.filter(
            status__in=(PlacementTask.Status.CREATED, PlacementTask.Status.PENDING)
        ).first()
        if existing is None:
            existing = open_qs.filter(status=PlacementTask.Status.IN_PROGRESS).first()

        if existing is not None:
            existing.quantity = int(existing.quantity) + add_qty
            if existing.batch_id is None and primary_batch_id is not None:
                existing.batch_id = primary_batch_id
            existing.save(update_fields=["quantity", "batch"])
            task_id = existing.pk
        else:
            task = PlacementTask.objects.create(
                planogram_id=pg.pk,
                product_id=pg.product_id,
                equipment_id=pg.slot.equipment_id,
                quantity=add_qty,
                batch_id=primary_batch_id,
                status=PlacementTask.Status.CREATED,
            )
            task_id = task.pk

        from .ws_broadcast import broadcast_placement_task_created, broadcast_task_pool

        payload = {
            "id": task_id,
            "product_id": pg.product_id,
            "product_name": pg.product.name,
            "equipment_name": pg.slot.equipment.name,
            "slot_id": slot.pk,
            "quantity": add_qty,
            "message": (
                f"Пополнить: {pg.product.name} — {add_qty} шт. → "
                f"{pg.slot.equipment.name}, полка {slot.row_index + 1}"
            ),
        }
        broadcast_task_pool("placement_task.created", payload)
        broadcast_placement_task_created(pg.slot.equipment.zone.store_id, payload)


def reconcile_for_product(product_id: int) -> None:
    for pg in Planogram.objects.filter(product_id=product_id).select_related(
        "slot",
        "slot__equipment",
        "product",
    ):
        reconcile_planogram(pg)


def adjust_slot_quantity(slot_id: int, delta: int) -> None:
    """Изменяет current_qty слота (продажа delta<0, выкладка delta>0)."""
    if delta == 0:
        return
    with transaction.atomic():
        slot = EquipmentSlot.objects.select_for_update().get(pk=slot_id)
        new_qty = max(0, int(slot.current_qty) + delta)
        slot.current_qty = new_qty
        slot.save(update_fields=["current_qty"])
    slot = EquipmentSlot.objects.get(pk=slot_id)
    reconcile_slot(slot)


def release_placement_task_reservation(product_id: int, qty: int) -> None:
    """Устаревший резерв: no-op (резерв при создании задачи отключён)."""
    del product_id, qty
