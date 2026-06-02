from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError

from .media_upload import save_task_photo
from .models import PlacementChatMessage, PlacementTask
from .ws_broadcast import broadcast_placement_task_chat

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


class PlacementChatError(ValidationError):
    pass


def _message_payload(message: PlacementChatMessage) -> dict:
    message = PlacementChatMessage.objects.select_related("sender").get(pk=message.pk)
    return {
        "id": str(message.pk),
        "placement_task_id": message.placement_task_id,
        "sender_id": message.sender_id,
        "sender_username": message.sender.username,
        "text": message.text,
        "image_url": message.image_url,
        "created_at": message.created_at.isoformat(),
    }


def post_placement_chat_message(
    task_id: int,
    sender: AbstractUser,
    text: str = "",
    image_file=None,
) -> PlacementChatMessage:
    text = (text or "").strip()
    if not text and image_file is None:
        raise PlacementChatError("Укажите текст или прикрепите изображение.")
    task = PlacementTask.objects.get(pk=task_id)
    if task.status in (PlacementTask.Status.COMPLETED, PlacementTask.Status.CANCELLED):
        raise PlacementChatError("Чат закрыт для завершённой задачи.")
    image_url = None
    if image_file is not None:
        image_url = save_task_photo(image_file, prefix="placement_chat")
    message = PlacementChatMessage.objects.create(
        placement_task=task,
        sender=sender,
        text=text,
        image_url=image_url,
    )
    payload = _message_payload(message)
    broadcast_placement_task_chat(task_id, payload)
    return message
