from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base


class Database:
    def __init__(self, url: str, echo: bool = False) -> None:
        self.is_sqlite = url.startswith("sqlite")
        if self.is_sqlite and "///" in url:
            path = url.split("///", 1)[1]
            if path and path != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)

        self.engine = create_async_engine(url, echo=echo, pool_pre_ping=not self.is_sqlite)
        if self.is_sqlite:
            event.listen(self.engine.sync_engine, "connect", _sqlite_pragmas)
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)

    def session(self) -> AsyncSession:
        """Read-only / manual session: ``async with db.session() as s``."""
        return self.sessionmaker()

    def begin(self) -> Any:
        """Transaction that commits on exit: ``async with db.begin() as s``."""
        return self.sessionmaker.begin()

    async def create_all(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        await self.engine.dispose()


def _sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=15000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()
