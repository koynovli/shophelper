from __future__ import annotations

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


@database_sync_to_async
def _get_user(token: str):
    authenticator = JWTAuthentication()
    try:
        validated = authenticator.get_validated_token(token)
        return authenticator.get_user(validated)
    except (InvalidToken, TokenError):
        return AnonymousUser()


class JwtAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode())
        token_list = query.get("token", [])
        if token_list:
            scope["user"] = await _get_user(token_list[0])
        elif scope.get("user") is None:
            scope["user"] = AnonymousUser()
        return await super().__call__(scope, receive, send)
