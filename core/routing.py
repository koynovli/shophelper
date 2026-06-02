from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r"ws/task-pool/$", consumers.TaskPoolConsumer.as_asgi()),
    re_path(r"ws/notifications/$", consumers.StoreNotificationsConsumer.as_asgi()),
    re_path(
        r"ws/chat/(?P<task_id>\d+)/$",
        consumers.PlacementTaskChatConsumer.as_asgi(),
    ),
    re_path(
        r"ws/staff-tasks/(?P<task_id>[0-9a-f-]+)/chat/$",
        consumers.StaffTaskChatConsumer.as_asgi(),
    ),
]
