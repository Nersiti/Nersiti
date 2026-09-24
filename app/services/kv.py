"""Settings admins can change right from the bot (ads, sponsor channels) — kept in the DB and cached."""

from __future__ import annotations

import time

from app.db import repo
from app.db.database import Database

AD_TEXT = "ad_text"
REQUIRED_CHANNELS = "required_channels"


class KVStore:
    def __init__(self, db: Database, ttl: float = 30.0) -> None:
        self.db = db
        self.ttl = ttl
        self._cache: dict[str, tuple[float, str | None]] = {}

    async def get(self, key: str) -> str | None:
        cached = self._cache.get(key)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        async with self.db.session() as s:
            value = await repo.kv_get(s, key)
        self._cache[key] = (time.monotonic() + self.ttl, value)
        return value

    async def set(self, key: str, value: str | None) -> None:
        async with self.db.begin() as s:
            await repo.kv_set(s, key, value)
        self._cache[key] = (time.monotonic() + self.ttl, value)
