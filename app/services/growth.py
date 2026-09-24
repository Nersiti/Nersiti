"""Growth mechanics: referrals, traffic source tags, broadcasts, showcase channel autoposting."""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import BufferedInputFile
from sqlalchemy import select, update

from app import keyboards as kb
from app import texts
from app.db.models import User
from app.services.images import build_request
from app.services.queue import PRIORITY_BACKGROUND
from app.utils import sanitize_tag

if TYPE_CHECKING:
    from app.context import Services

log = logging.getLogger(__name__)


async def bot_link(bot: Bot, payload: str = "") -> str:
    me = await bot.me()
    return f"https://t.me/{me.username}" + (f"?start={payload}" if payload else "")


async def apply_start_payload(ctx: Services, user: User, payload: str) -> str | None:
    """Handle the /start parameter of a new user: ``ref_<id>`` is a referral, anything else is a source tag."""
    settings = ctx.settings
    if payload.startswith("ref_"):
        ref = payload[4:]
        if not ref.isdigit() or int(ref) == user.id:
            return None
        referrer_id = int(ref)
        async with ctx.db.begin() as s:
            if not await s.scalar(select(User.id).where(User.id == referrer_id)):
                return None
            result = await s.execute(
                update(User)
                .where(User.id == user.id, User.referrer_id.is_(None))
                .values(
                    referrer_id=referrer_id,
                    source="ref",
                    credits=User.credits + settings.ref_bonus_invitee,
                )
            )
        if result.rowcount != 1 or not settings.ref_bonus_invitee:
            return None
        return texts.referral_welcome(settings.ref_bonus_invitee)

    tag = sanitize_tag(payload[4:] if payload.startswith("src_") else payload)
    if tag:
        async with ctx.db.begin() as s:
            await s.execute(update(User).where(User.id == user.id, User.source.is_(None)).values(source=tag))
    return None


async def reward_inviter(bot: Bot, ctx: Services, user: User) -> None:
    """Pay the inviter once the friend makes their first real request (protection from fake accounts)."""
    if not user.referrer_id or user.referral_rewarded:
        return
    bonus = ctx.settings.ref_bonus_inviter
    async with ctx.db.begin() as s:
        result = await s.execute(
            update(User).where(User.id == user.id, User.referral_rewarded.is_(False)).values(referral_rewarded=True)
        )
        if result.rowcount != 1:
            return
        if bonus:
            await s.execute(
                update(User)
                .where(User.id == user.referrer_id)
                .values(credits=User.credits + bonus, ref_earned=User.ref_earned + bonus)
            )
    user.referral_rewarded = True
    if bonus:
        try:
            await bot.send_message(user.referrer_id, texts.referral_reward(bonus, user.first_name or "Друг"))
        except TelegramAPIError:
            pass


async def run_broadcast(bot: Bot, ctx: Services, admin_chat: int, from_chat: int, message_id: int) -> None:
    sent = failed = blocked = 0
    last_id = 0
    while True:
        async with ctx.db.session() as s:
            ids = (
                await s.scalars(
                    select(User.id)
                    .where(User.id > last_id, User.is_blocked.is_(False), User.is_banned.is_(False))
                    .order_by(User.id)
                    .limit(500)
                )
            ).all()
        if not ids:
            break
        for user_id in ids:
            last_id = user_id
            for _attempt in range(2):
                try:
                    await bot.copy_message(chat_id=user_id, from_chat_id=from_chat, message_id=message_id)
                    sent += 1
                    break
                except TelegramRetryAfter as e:
                    await asyncio.sleep(e.retry_after + 1)
                except TelegramForbiddenError:
                    blocked += 1
                    async with ctx.db.begin() as s:
                        await s.execute(update(User).where(User.id == user_id).values(is_blocked=True))
                    break
                except TelegramAPIError:
                    failed += 1
                    break
            await asyncio.sleep(0.05)  # ~20 сообщений в секунду — в пределах лимитов Telegram
    await bot.send_message(
        admin_chat,
        f"📬 Рассылка завершена.\n✅ Доставлено: {sent}\n🚫 Заблокировали бота: {blocked}\n⚠️ Ошибки: {failed}",
    )


@dataclass(frozen=True)
class ShowcaseItem:
    caption: str
    prompt: str
    style: str


def load_showcase_items(path: str) -> list[ShowcaseItem]:
    """Line format: ``Russian caption | English prompt | style``."""
    file = Path(path)
    if not file.exists():
        return []
    items = []
    for line in file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            continue
        items.append(ShowcaseItem(parts[0], parts[1], parts[2] if len(parts) > 2 else "auto"))
    return items


async def post_showcase(bot: Bot, ctx: Services) -> bool:
    settings = ctx.settings
    items = load_showcase_items(settings.showcase_prompts_file)
    if not settings.showcase_channel or not items:
        return False
    item = random.choice(items)
    req = build_request(settings, item.prompt, item.style, "1x1")
    image = await ctx.gen.submit(lambda: ctx.images.generate(req), priority=PRIORITY_BACKGROUND)
    link = await bot_link(bot, "src_showcase")
    await bot.send_photo(
        chat_id=settings.showcase_channel,
        photo=BufferedInputFile(image, "art.png"),
        caption=texts.showcase_caption(item.caption, settings.bot_name),
        reply_markup=kb.url_kb("🎨 Создать свою картинку", link),
    )
    return True


async def showcase_loop(bot: Bot, ctx: Services) -> None:
    interval = max(ctx.settings.showcase_interval_minutes, 10) * 60
    while True:
        await asyncio.sleep(interval)
        try:
            await post_showcase(bot, ctx)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Showcase post failed")
