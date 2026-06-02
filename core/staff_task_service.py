from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .media_upload import save_task_photo
from .models import ChatMessage, StaffTask, User, Zone
from .ws_broadcast import broadcast_staff_task_chat, broadcast_task_pool

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser


class StaffTaskError(ValidationError):
    pass


def create_staff_task(
    manager: AbstractUser,
    *,
    title: str,
    description: str = "",
    assigned_to: User | None = None,
    zone: Zone | None = None,
    equipment=None,
    slot=None,
    requires_photo: bool = False,
) -> StaffTask:
    if getattr(manager, "role", None) != User.Role.ADMIN:
        raise StaffTaskError("Создавать поручения может только менеджер.")
    task = StaffTask.objects.create(
        title=title,
        description=description,
        created_by=manager,
        assigned_to=assigned_to,
        zone=zone,
        equipment=equipment,
        slot=slot,
        requires_photo=requires_photo,
        status=StaffTask.Status.CREATED,
    )
    broadcast_task_pool(
        "staff_task.created",
        {"id": str(task.pk), "title": task.title, "status": task.status},
    )
    if assigned_to_id := task.assigned_to_id:
        from .ws_broadcast import broadcast_to_user

        broadcast_to_user(
            assigned_to_id,
            "staff_task.created",
            {"id": str(task.pk), "title": task.title},
        )
    return task


def accept_staff_task(task_id: uuid.UUID, user: AbstractUser) -> StaffTask:
    with transaction.atomic():
        task = StaffTask.objects.select_for_update().get(pk=task_id)
        if task.status != StaffTask.Status.CREATED:
            raise StaffTaskError("Поручение можно взять только в статусе CREATED.")
        if task.assigned_to_id and task.assigned_to_id != user.pk:
            raise StaffTaskError("Поручение назначено другому сотруднику.")
        task.assigned_to = user
        task.status = StaffTask.Status.IN_PROGRESS
        task.save(update_fields=["assigned_to", "status"])
    broadcast_task_pool(
        "staff_task.updated",
        {"id": str(task.pk), "status": task.status},
    )
    return task


def complete_staff_task(
    task_id: uuid.UUID,
    user: AbstractUser,
    photo_file=None,
) -> StaffTask:
    with transaction.atomic():
        task = StaffTask.objects.select_for_update().get(pk=task_id)
        if task.status != StaffTask.Status.IN_PROGRESS:
            raise StaffTaskError("Завершить можно только поручение IN_PROGRESS.")
        if task.assigned_to_id and task.assigned_to_id != user.pk:
            raise StaffTaskError("Поручение назначено другому сотруднику.")
        if task.requires_photo and photo_file is None:
            raise StaffTaskError("Для этого поручения требуется фотоотчёт.")
        if photo_file is not None:
            task.photo_url = save_task_photo(photo_file, prefix="staff_reports")
        task.status = StaffTask.Status.COMPLETED
        task.completed_at = timezone.now()
        task.save(update_fields=["photo_url", "status", "completed_at"])
    broadcast_task_pool(
        "staff_task.completed",
        {"id": str(task.pk), "status": task.status},
    )
    return task


def cancel_staff_task(task_id: uuid.UUID, manager: AbstractUser) -> StaffTask:
    if getattr(manager, "role", None) != User.Role.ADMIN:
        raise StaffTaskError("Отменять поручения может только менеджер.")
    with transaction.atomic():
        task = StaffTask.objects.select_for_update().get(pk=task_id)
        if task.status in (StaffTask.Status.COMPLETED, StaffTask.Status.CANCELLED):
            raise StaffTaskError("Поручение уже закрыто.")
        task.status = StaffTask.Status.CANCELLED
        task.save(update_fields=["status"])
    broadcast_task_pool(
        "staff_task.updated",
        {"id": str(task.pk), "status": task.status},
    )
    return task


def _chat_message_payload(message: ChatMessage) -> dict:
    message = ChatMessage.objects.select_related("sender").get(pk=message.pk)
    return {
        "id": str(message.pk),
        "staff_task_id": str(message.staff_task_id),
        "sender_id": message.sender_id,
        "sender_username": message.sender.username,
        "text": message.text,
        "image_url": message.image_url,
        "created_at": message.created_at.isoformat(),
    }


def post_chat_message(
    task_id: uuid.UUID,
    sender: AbstractUser,
    text: str = "",
    image_file=None,
) -> ChatMessage:
    text = (text or "").strip()
    if not text and image_file is None:
        raise StaffTaskError("Укажите текст сообщения или прикрепите изображение.")
    task = StaffTask.objects.get(pk=task_id)
    if task.status in (StaffTask.Status.COMPLETED, StaffTask.Status.CANCELLED):
        raise StaffTaskError("Чат закрыт для завершённого поручения.")
    image_url = None
    if image_file is not None:
        image_url = save_task_photo(image_file, prefix="chat_attachments")
    message = ChatMessage.objects.create(
        staff_task=task,
        sender=sender,
        text=text,
        image_url=image_url,
    )
    broadcast_staff_task_chat(str(task.pk), _chat_message_payload(message))
    return message
