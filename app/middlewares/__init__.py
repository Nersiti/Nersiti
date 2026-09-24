from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject, Update
from aiogram.types import User as TgUser

from app.context import Services
from app.db import repo


class UserMiddleware(BaseMiddleware):
    """Loads (or creates) the user and passes them to handlers as ``user``."""

    def __init__(self, ctx: Services) -> None:
        self.ctx = ctx

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return await handler(event, data)
        user, is_new = await repo.get_or_create_user(self.ctx.db, tg_user, self.ctx.settings.start_bonus)
        if user.is_banned and not self.ctx.settings.is_admin(user.id) and not _is_payment(event):
            return None
        data["user"] = user
        data["is_new_user"] = is_new
        return await handler(event, data)


def _is_payment(event: TelegramObject) -> bool:
    """Payments are always processed, even from a banned user — otherwise the money is lost."""
    if not isinstance(event, Update):
        return False
    return bool(event.pre_checkout_query or (event.message and event.message.successful_payment))


class ThrottlingMiddleware(BaseMiddleware):
    """Silently drops messages sent faster than once every ``rate`` seconds."""

    def __init__(self, rate: float) -> None:
        self.rate = rate
        self._last: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.from_user and not event.successful_payment:
            now = time.monotonic()
            user_id = event.from_user.id
            if now - self._last.get(user_id, 0.0) < self.rate:
                return None
            self._last[user_id] = now
            if len(self._last) > 50000:
                self._last = {k: v for k, v in self._last.items() if now - v < 60}
        return await handler(event, data)
