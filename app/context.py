from __future__ import annotations

import asyncio
import secrets
from collections import OrderedDict
from dataclasses import dataclass, field

from app.config import Settings
from app.db.database import Database
from app.game.auction import AuctionService
from app.game.service import GameService
from app.services.channels import ChannelGate
from app.services.images import ImageBackend
from app.services.kv import KVStore
from app.services.llm import LLMClient
from app.services.payments.service import PaymentService
from app.services.queue import GenerationQueue


class TokenStore:
    """Short tokens for buttons: callback_data holds up to 64 bytes, and a word can be longer."""

    def __init__(self, capacity: int = 50000) -> None:
        self.capacity = capacity
        self._items: OrderedDict[str, str] = OrderedDict()

    def put(self, value: str) -> str:
        token = secrets.token_urlsafe(6)
        self._items[token] = value
        while len(self._items) > self.capacity:
            self._items.popitem(last=False)
        return token

    def get(self, token: str) -> str | None:
        return self._items.get(token)


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
    game: GameService
    auctions: AuctionService
    tokens: TokenStore = field(default_factory=TokenStore)
    busy: set[int] = field(default_factory=set)
    tasks: list[asyncio.Task[None]] = field(default_factory=list)
    pending_broadcasts: dict[int, tuple[int, int]] = field(default_factory=dict)
    reported: set[tuple[int, int]] = field(default_factory=set)  # (игрок, карта) — одна жалоба на карту
    next_reminders_at: float = 0.0
