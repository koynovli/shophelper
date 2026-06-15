from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import transaction
from django.utils import timezone

from .models import SupplyOrder, SupplyReceivingTask, User
from .ws_broadcast import broadcast_task_pool


class SupplyOrderError(Exception):
    pass


def cancel_supply_order(
    order_id: int,
    manager: AbstractUser,
    *,
    reason_code: str,
    reason_note: str = "",
) -> SupplyOrder:
    if getattr(manager, "role", None) != User.Role.ADMIN:
        raise SupplyOrderError("Отменять заказы может только менеджер.")

    valid_codes = {choice.value for choice in SupplyOrder.CancellationReason}
    if reason_code not in valid_codes:
        raise SupplyOrderError("Укажите корректную причину отмены.")

    note = (reason_note or "").strip()
    if reason_code == SupplyOrder.CancellationReason.OTHER and not note:
        raise SupplyOrderError("Для причины «Другое» укажите комментарий.")

    with transaction.atomic():
        order = (
            SupplyOrder.objects.select_for_update()
            .select_related("receiving_task")
            .get(pk=order_id)
        )
        if order.status != SupplyOrder.Status.ORDERED:
            raise SupplyOrderError(
                "Отменить можно только заказ в статусе «В пути»."
            )

        order.status = SupplyOrder.Status.CANCELLED
        order.cancellation_reason_code = reason_code
        order.cancellation_reason_note = note
        order.cancelled_at = timezone.now()
        order.cancelled_by = manager
        order.save(
            update_fields=[
                "status",
                "cancellation_reason_code",
                "cancellation_reason_note",
                "cancelled_at",
                "cancelled_by",
            ]
        )

        receiving_task = getattr(order, "receiving_task", None)
        if receiving_task is not None and receiving_task.status in (
            SupplyReceivingTask.Status.CREATED,
            SupplyReceivingTask.Status.IN_PROGRESS,
        ):
            receiving_task.status = SupplyReceivingTask.Status.CANCELLED
            receiving_task.save(update_fields=["status"])
            broadcast_task_pool(
                "receiving_task.updated",
                {"id": receiving_task.pk, "status": receiving_task.status},
            )

    return order
