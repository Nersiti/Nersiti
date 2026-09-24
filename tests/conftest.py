from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update
from sqlalchemy import select

from app.config import Settings
from app.context import Services
from app.db import repo
from app.db.models import Base, Card, User
from app.handlers import ALL_ROUTERS
from app.main import build_dispatcher, build_services, shutdown, startup
from tests import fake
from tests.fake import FakeSession

ADMIN_ID = 1


def make_settings(tmp_path: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "bot_token": "42:TEST",
        # TEST_DATABASE_URL=postgresql+asyncpg://... — прогнать тесты на PostgreSQL
        "database_url": os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{tmp_path}/test.db",
        "llm_backend": "mock",
        "image_backend": "mock",
        "admin_ids": [ADMIN_ID],
        "auction_enabled": False,
        "top_cache_seconds": 0,
        "throttle_seconds": 0,
        "support_contact": "@support",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


@dataclass
class BotHarness:
    bot: Bot
    dp: Dispatcher
    ctx: Services
    session: FakeSession

    async def feed(self, update: Update) -> None:
        await self.dp.feed_update(self.bot, update)

    async def card(self, word: str) -> Card:
        async with self.ctx.db.session() as s:
            card = await s.scalar(select(Card).where(Card.word == word))
        assert card is not None
        return card

    async def user(self, user_id: int) -> User:
        async with self.ctx.db.session() as s:
            user = await repo.get_user(s, user_id)
        assert user is not None
        return user


@pytest.fixture
async def harness_factory(tmp_path: Path) -> AsyncIterator[Callable[..., Any]]:
    created: list[BotHarness] = []

    fake._names.clear()

    async def factory(**overrides: Any) -> BotHarness:
        # роутеры — модульные синглтоны; в тестах собираем новый диспетчер, поэтому отвязываем их
        for router in ALL_ROUTERS:
            router._parent_router = None
        ctx = build_services(make_settings(tmp_path, **overrides))
        if not ctx.db.is_sqlite:
            async with ctx.db.engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
        session = FakeSession()
        bot = Bot("42:TEST", session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        dp = build_dispatcher(ctx)
        await startup(bot, ctx, configure_bot=False, background=False)
        harness = BotHarness(bot, dp, ctx, session)
        created.append(harness)
        return harness

    yield factory
    for h in created:
        await shutdown(h.ctx)


@pytest.fixture
async def harness(harness_factory: Callable[..., Any]) -> BotHarness:
    return await harness_factory()
