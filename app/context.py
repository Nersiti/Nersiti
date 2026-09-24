from __future__ import annotations

import asyncio
import secrets
from collections import OrderedDict
from dataclasses import dataclass, field

from app.config import Settings
from app.db.database import Database
from app.services.channels import ChannelGate
from app.services.images import ImageBackend
from app.services.kv import KVStore
from app.services.llm import LLMClient
from app.services.payments.service import PaymentService
from app.services.queue import GenerationQueue


class PromptStore:
    """Remembers recent image prompts for the "Another variant" button (in memory)."""

    def __init__(self, capacity: int = 20000) -> None:
        self.capacity = capacity
        self._items: OrderedDict[str, tuple[int, str]] = OrderedDict()

    def put(self, user_id: int, prompt: str) -> str:
        token = secrets.token_urlsafe(8)
        self._items[token] = (user_id, prompt)
        while len(self._items) > self.capacity:
            self._items.popitem(last=False)
        return token

    def get(self, token: str, user_id: int) -> str | None:
        item = self._items.get(token)
        if item is None or item[0] != user_id:
            return None
        return item[1]


@dataclass
class Services:
    settings: Settings
    db: Database
    kv: KVStore
    llm: LLMClient
    images: ImageBackend
    gen: GenerationQueue
    payments: PaymentService
    gate: ChannelGate
    prompts: PromptStore = field(default_factory=PromptStore)
    busy: set[int] = field(default_factory=set)
    tasks: list[asyncio.Task[None]] = field(default_factory=list)
    pending_broadcasts: dict[int, tuple[int, int]] = field(default_factory=dict)
    draft_streaming: bool = True
