from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, event, inspect, literal, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base

log = logging.getLogger(__name__)


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

    async def create_all(self) -> list[str]:
        """Create tables and add new columns to existing ones (additive auto-migration)."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            added = await conn.run_sync(add_missing_columns)
        if added:
            log.info("Database migrated, added columns: %s", ", ".join(added))
        return added

    async def close(self) -> None:
        await self.engine.dispose()


def add_missing_columns(conn: Connection) -> list[str]:
    """ALTER TABLE ... ADD COLUMN for model fields that the database doesn't have yet.

    Lets you add new fields to the models without a separate migration tool. Renames and deletions aren't supported —
    that's intentional: data is never deleted automatically.
    """
    inspector = inspect(conn)
    quote = conn.dialect.identifier_preparer.quote
    added: list[str] = []
    for table in Base.metadata.sorted_tables:
        existing = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing:
                continue
            ddl = f"ALTER TABLE {quote(table.name)} ADD COLUMN {quote(column.name)} {column.type.compile(conn.dialect)}"
            default = column.default
            if default is not None and getattr(default, "is_scalar", False):
                value = literal(default.arg).compile(dialect=conn.dialect, compile_kwargs={"literal_binds": True})
                ddl += f" DEFAULT {value}"
                if not column.nullable:
                    ddl += " NOT NULL"
            conn.execute(text(ddl))
            added.append(f"{table.name}.{column.name}")
        new_columns = {name.split(".", 1)[1] for name in added if name.startswith(f"{table.name}.")}
        for index in table.indexes:
            if new_columns & {column.name for column in index.columns}:
                index.create(conn, checkfirst=True)
    return added


def _sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=15000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()
