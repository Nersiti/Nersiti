"""Mandatory channel subscription (grow your own channel / sell sponsor slots)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError

from app.config import Settings
from app.services.kv import REQUIRED_CHANNELS, KVStore

log = logging.getLogger(__name__)

OK_CACHE_SECONDS = 30 * 60


@dataclass(frozen=True)
class Channel:
    chat: int | str
    url: str


def parse_channels(entries: list[str]) -> list[Channel]:
    """Format: ``@channel`` or ``-100123456|https://t.me/+invite``."""
    result: list[Channel] = []
    for raw in entries:
        ref, _, url = raw.strip().partition("|")
        ref = ref.strip()
        if not ref:
            continue
        if ref.lstrip("-").isdigit():
            if not url:
                log.warning("Channel %s has no invite link, skipped", ref)
                continue
            result.append(Channel(int(ref), url.strip()))
        else:
            name = ref.lstrip("@").removeprefix("https://t.me/")
            result.append(Channel(f"@{name}", url.strip() or f"https://t.me/{name}"))
    return result


class ChannelGate:
    def __init__(self, settings: Settings, kv: KVStore) -> None:
        self.settings = settings
        self.kv = kv
        self._ok_until: dict[int, float] = {}

    async def channels(self) -> list[Channel]:
        stored = await self.kv.get(REQUIRED_CHANNELS)
        entries = self.settings.required_channels if stored is None else [x for x in stored.split(",") if x.strip()]
        return parse_channels(entries)

    def forget(self, user_id: int) -> None:
        self._ok_until.pop(user_id, None)

    async def missing(self, bot: Bot, user_id: int) -> list[Channel]:
        channels = await self.channels()
        if not channels or self._ok_until.get(user_id, 0) > time.monotonic():
            return []
        missing: list[Channel] = []
        for channel in channels:
            try:
                member = await bot.get_chat_member(channel.chat, user_id)
            except TelegramAPIError as e:
                log.warning("Can't check subscription to %s (bot must be an admin there): %s", channel.chat, e)
                continue
            left = member.status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED)
            restricted_out = member.status == ChatMemberStatus.RESTRICTED and not getattr(member, "is_member", True)
            if left or restricted_out:
                missing.append(channel)
        if not missing:
            self._ok_until[user_id] = time.monotonic() + OK_CACHE_SECONDS
        return missing
