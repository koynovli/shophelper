from __future__ import annotations

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer


class TaskPoolConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close()
            return
        self.user_group = f"user_{user.pk}"
        self.pool_group = "task_pool"
        await self.channel_layer.group_add(self.user_group, self.channel_name)
        await self.channel_layer.group_add(self.pool_group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "user_group"):
            await self.channel_layer.group_discard(self.user_group, self.channel_name)
        if hasattr(self, "pool_group"):
            await self.channel_layer.group_discard(self.pool_group, self.channel_name)

    async def placement_task_created(self, event):
        await self.send_json({"event": "placement_task.created", "data": event["payload"]})

    async def placement_task_updated(self, event):
        await self.send_json({"event": "placement_task.updated", "data": event["payload"]})

    async def placement_task_completed(self, event):
        await self.send_json({"event": "placement_task.completed", "data": event["payload"]})

    async def staff_task_created(self, event):
        await self.send_json({"event": "staff_task.created", "data": event["payload"]})

    async def staff_task_updated(self, event):
        await self.send_json({"event": "staff_task.updated", "data": event["payload"]})

    async def staff_task_completed(self, event):
        await self.send_json({"event": "staff_task.completed", "data": event["payload"]})


class StoreNotificationsConsumer(AsyncJsonWebsocketConsumer):
    """ws/notifications/ — уведомления по магазину (новые задачи на выкладку)."""

    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close()
            return
        store_id = await self._resolve_store_id(user)
        if store_id is None:
            await self.close()
            return
        self.store_group = f"store_{store_id}"
        await self.channel_layer.group_add(self.store_group, self.channel_name)
        await self.accept()

    @database_sync_to_async
    def _resolve_store_id(self, user):
        if user.store_id:
            return user.store_id
        from .models import Store

        return Store.objects.order_by("pk").values_list("pk", flat=True).first()

    async def disconnect(self, close_code):
        if hasattr(self, "store_group"):
            await self.channel_layer.group_discard(self.store_group, self.channel_name)

    async def notification_placement(self, event):
        await self.send_json(
            {"event": "placement_task.created", "data": event["payload"]},
        )


@database_sync_to_async
def _post_placement_chat_sync(task_id: int, user, text: str, image_file=None):
    from .placement_chat_service import PlacementChatError, post_placement_chat_message

    try:
        message = post_placement_chat_message(
            int(task_id),
            user,
            text=text,
            image_file=image_file,
        )
    except PlacementChatError as exc:
        return None, str(exc)
    from .placement_chat_service import _message_payload

    return _message_payload(message), None


class PlacementTaskChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close()
            return
        self.task_id = self.scope["url_route"]["kwargs"]["task_id"]
        self.group_name = f"placement_task_{self.task_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        text = (content.get("text") or "").strip()
        if not text:
            return
        user = self.scope["user"]
        payload, error = await _post_placement_chat_sync(self.task_id, user, text)
        if error:
            await self.send_json({"event": "error", "detail": error})
            return
        await self.send_json({"event": "chat.message", "data": payload})

    async def chat_message(self, event):
        await self.send_json({"event": "chat.message", "data": event["payload"]})


@database_sync_to_async
def _post_chat_message_sync(task_id: str, user, text: str, image_file=None):
    from .staff_task_service import StaffTaskError, post_chat_message

    try:
        message = post_chat_message(task_id, user, text=text, image_file=image_file)
    except StaffTaskError as exc:
        return None, str(exc)
    from .staff_task_service import _chat_message_payload

    return _chat_message_payload(message), None


class StaffTaskChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if user is None or not user.is_authenticated:
            await self.close()
            return
        self.task_id = self.scope["url_route"]["kwargs"]["task_id"]
        self.group_name = f"staff_task_{self.task_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        text = (content.get("text") or "").strip()
        if not text:
            return
        user = self.scope["user"]
        payload, error = await _post_chat_message_sync(self.task_id, user, text)
        if error:
            await self.send_json({"event": "error", "detail": error})
            return
        await self.send_json({"event": "chat.message", "data": payload})

    async def chat_message(self, event):
        await self.send_json({"event": "chat.message", "data": event["payload"]})
