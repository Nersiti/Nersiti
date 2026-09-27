import os

# Must be set before any app module reads settings.
os.environ["ENV"] = "test"
os.environ["BOT_TOKEN"] = "123456789:TEST-token_abcdefghijklmnopqrstuvwxy"
os.environ["BOT_USERNAME"] = "test_bot"
os.environ["WEBHOOK_SECRET"] = "test-secret"
os.environ["DOMAIN"] = "game.test"
os.environ["ADMIN_IDS"] = "999"
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://game:game@localhost:5432/game_test"
)
os.environ["REDIS_URL"] = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")

from collections.abc import AsyncIterator  # noqa: E402
from datetime import datetime  # noqa: E402
from typing import Any  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from aiogram import Bot  # noqa: E402
from aiogram.client.session.base import BaseSession  # noqa: E402
from aiogram.methods import TelegramMethod  # noqa: E402
from aiogram.types import Chat, Message  # noqa: E402


class MockSession(BaseSession):
    """Records Bot API calls instead of sending them to Telegram."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []
        self.responses: dict[str, Any] = {}

    async def make_request(self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None):
        self.calls.append(method)
        name = type(method).__name__
        if name in self.responses:
            value = self.responses[name]
            return value(method) if callable(value) else value
        if name == "SendMessage":
            return Message(
                message_id=len(self.calls),
                date=datetime.now(),
                chat=Chat(id=method.chat_id, type="private"),
                text=method.text,
            )
        return True

    async def close(self) -> None:
        pass

    async def stream_content(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError

    def of_type(self, name: str) -> list[Any]:
        return [c for c in self.calls if type(c).__name__ == name]


@pytest.fixture(scope="session")
async def _schema() -> AsyncIterator[None]:
    from app import models  # noqa: F401
    from app.db import Base, dispose_engine, get_engine
    from app.redis_client import close_redis

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await close_redis()
    await dispose_engine()


@pytest.fixture(autouse=True)
async def _clean_state(_schema) -> None:
    from sqlalchemy import text

    from app.db import Base, get_engine
    from app.redis_client import get_redis

    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with get_engine().begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    await get_redis().flushdb()

    from app.game import state, world_service

    world_service.reset_cache()
    state.reset_caches()


@pytest.fixture
async def db():
    from app.db import get_sessionmaker

    async with get_sessionmaker()() as session:
        yield session


@pytest.fixture
def bot_session() -> MockSession:
    from app.bot.instance import get_bot

    session = MockSession()
    get_bot().session = session
    return session


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
