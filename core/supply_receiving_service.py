from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date

from .models import (
    Inventory,
    ProductBatch,
    SupplyOrder,
    SupplyOrderItem,
    SupplyReceivingTask,
    User,
)
from .ws_broadcast import broadcast_task_pool


class SupplyReceivingError(Exception):
    pass


def parse_expiration_date(raw) -> date | None:
    if isinstance(raw, date):
        return raw
    if isinstance(raw, str):
        return parse_date(raw.strip())
    return None


def execute_supply_order_receive(
    order: SupplyOrder,
    *,
    lines: list[dict],
    received_by: AbstractUser | None,
) -> SupplyOrder:
    """
    lines: [{item_id, expiration_date, actual_quantity, discrepancy_note?}, ...]
    """
    if order.status == SupplyOrder.Status.RECEIVED:
        raise SupplyReceivingError("Заказ уже принят.")
    if order.status != SupplyOrder.Status.ORDERED:
        raise SupplyReceivingError(
            "Приёмка доступна только для заказа в статусе «В пути»."
        )

    order_items = {item.pk: item for item in order.items.select_related("product")}
    if set(order_items.keys()) != {int(line["item_id"]) for line in lines}:
        raise SupplyReceivingError(
            "Нужно указать данные приёмки по каждой строке заказа."
        )

    total_cost = Decimal("0")
    has_discrepancies = False

    with transaction.atomic():
        order = SupplyOrder.objects.select_for_update().get(pk=order.pk)

        for line in lines:
            item_id = int(line["item_id"])
            item = order_items.get(item_id)
            if item is None:
                raise SupplyReceivingError(
                    f"Позиция заказа id={item_id} не найдена."
                )

            exp_raw = line.get("expiration_date")
            if exp_raw is None:
                raise SupplyReceivingError(
                    f"Укажите срок годности для позиции id={item_id}."
                )
            exp_date = parse_expiration_date(exp_raw)
            if exp_date is None:
                raise SupplyReceivingError(
                    "Некорректная дата expiration_date (ожидается YYYY-MM-DD)."
                )

            try:
                actual_qty = int(line.get("actual_quantity", item.quantity))
            except (TypeError, ValueError) as exc:
                raise SupplyReceivingError(
                    "Поле actual_quantity должно быть целым числом."
                ) from exc
            if actual_qty < 0:
                raise SupplyReceivingError("actual_quantity не может быть отрицательным.")

            note = (line.get("discrepancy_note") or "").strip()
            if actual_qty != item.quantity:
                has_discrepancies = True
                if not note:
                    product_label = item.product.name if item.product_id else f"id={item_id}"
                    raise SupplyReceivingError(
                        f"Укажите примечание по расхождению для «{product_label}» "
                        f"(заказано {item.quantity}, факт {actual_qty})."
                    )

            item = SupplyOrderItem.objects.select_for_update().get(pk=item_id)
            item.actual_quantity = actual_qty
            item.discrepancy_note = note
            item.save(update_fields=["actual_quantity", "discrepancy_note"])

            line_cost = Decimal(actual_qty) * item.purchase_price
            total_cost += line_cost

            if actual_qty == 0:
                continue

            batch = ProductBatch.objects.create(
                product=item.product,
                store=order.store,
                supply_item=item,
                purchase_price=item.purchase_price,
                initial_quantity=actual_qty,
                current_quantity=actual_qty,
                manufacture_date=None,
                expiration_date=exp_date,
                is_active=True,
            )
            Inventory.objects.update_or_create(
                store=order.store,
                product=item.product,
                batch=batch,
                defaults={
                    "quantity": actual_qty,
                    "status": Inventory.LocationStatus.WAREHOUSE,
                },
            )

        order.status = SupplyOrder.Status.RECEIVED
        order.received_at = timezone.now()
        order.total_cost = total_cost
        order.received_by = received_by if received_by and received_by.is_authenticated else None
        order.has_discrepancies = has_discrepancies
        order.save(
            update_fields=[
                "status",
                "received_at",
                "total_cost",
                "received_by",
                "has_discrepancies",
            ]
        )

    return order


def create_receiving_task(
    order: SupplyOrder,
    created_by: AbstractUser | None,
    *,
    assigned_to: User | None = None,
) -> SupplyReceivingTask:
    if order.status != SupplyOrder.Status.ORDERED:
        raise SupplyReceivingError(
            "Задача приёмки создаётся только для заказа «В пути»."
        )
    task, created = SupplyReceivingTask.objects.get_or_create(
        supply_order=order,
        defaults={
            "status": SupplyReceivingTask.Status.CREATED,
            "created_by": created_by if created_by and created_by.is_authenticated else None,
            "assigned_to": assigned_to,
        },
    )
    if not created and task.status == SupplyReceivingTask.Status.CANCELLED:
        task.status = SupplyReceivingTask.Status.CREATED
        task.assigned_to = assigned_to
        task.save(update_fields=["status", "assigned_to"])

    broadcast_task_pool(
        "receiving_task.created",
        {
            "id": str(task.pk),
            "supply_order_id": order.pk,
            "title": f"Приёмка заказа #{order.pk}",
        },
    )
    if assigned_to_id := task.assigned_to_id:
        from .ws_broadcast import broadcast_to_user

        broadcast_to_user(
            assigned_to_id,
            "receiving_task.created",
            {"id": str(task.pk), "supply_order_id": order.pk},
        )
    return task


def accept_receiving_task(task_id: int, user: AbstractUser) -> SupplyReceivingTask:
    with transaction.atomic():
        task = SupplyReceivingTask.objects.select_for_update().get(pk=task_id)
        if task.status != SupplyReceivingTask.Status.CREATED:
            raise SupplyReceivingError("Задачу можно взять только в статусе CREATED.")
        if task.assigned_to_id and task.assigned_to_id != user.pk:
            raise SupplyReceivingError("Задача назначена другому сотруднику.")
        task.assigned_to = user
        task.status = SupplyReceivingTask.Status.IN_PROGRESS
        task.save(update_fields=["assigned_to", "status"])
    broadcast_task_pool(
        "receiving_task.updated",
        {"id": str(task.pk), "status": task.status},
    )
    return task


def complete_receiving_task(
    task_id: int,
    user: AbstractUser,
    lines: list[dict],
) -> SupplyReceivingTask:
    with transaction.atomic():
        task = SupplyReceivingTask.objects.select_for_update().select_related(
            "supply_order"
        ).get(pk=task_id)
        if task.status != SupplyReceivingTask.Status.IN_PROGRESS:
            raise SupplyReceivingError(
                "Завершить можно только задачу в статусе IN_PROGRESS."
            )
        if task.assigned_to_id and task.assigned_to_id != user.pk:
            raise SupplyReceivingError("Задача назначена другому сотруднику.")

        order = task.supply_order
        execute_supply_order_receive(
            order,
            lines=lines,
            received_by=user,
        )
        task.status = SupplyReceivingTask.Status.COMPLETED
        task.completed_at = timezone.now()
        task.save(update_fields=["status", "completed_at"])

    broadcast_task_pool(
        "receiving_task.completed",
        {"id": str(task.pk), "supply_order_id": task.supply_order_id},
    )
    return task
