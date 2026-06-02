from __future__ import annotations

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def _send(group: str, event_type: str, payload: dict) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    # Channels: type → имя метода consumer (точки → подчёркивания)
    handler_type = event_type.replace(".", "_")
    async_to_sync(channel_layer.group_send)(
        group,
        {"type": handler_type, "payload": payload},
    )


def broadcast_to_user(user_id: int, event_type: str, payload: dict) -> None:
    _send(f"user_{user_id}", event_type, payload)


def broadcast_task_pool(event_type: str, payload: dict) -> None:
    _send("task_pool", event_type, payload)


def broadcast_staff_task_chat(staff_task_id: str, payload: dict) -> None:
    _send(f"staff_task_{staff_task_id}", "chat.message", payload)


def broadcast_placement_task_created(store_id: int, payload: dict) -> None:
    """Уведомление сотрудникам магазина (ws/notifications/)."""
    _send(f"store_{store_id}", "notification.placement", payload)


def broadcast_placement_task_chat(placement_task_id: int, payload: dict) -> None:
    _send(f"placement_task_{placement_task_id}", "chat.message", payload)
