import os
from urllib.parse import urlparse

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "shophelper.settings")

django_asgi_app = get_asgi_application()

from core.routing import websocket_urlpatterns  # noqa: E402
from core.ws_auth import JwtAuthMiddleware  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": JwtAuthMiddleware(AuthMiddlewareStack(URLRouter(websocket_urlpatterns))),
    }
)
