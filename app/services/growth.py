"""Growth mechanics: referrals, traffic source tags, broadcasts, the "World of Words Chronicle" channel."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup
from sqlalchemy import case, or_, select, update

from app import texts
from app.db.models import User
from app.utils import local_today, sanitize_tag

if TYPE_CHECKING:
    from app.context import Services

log = logging.getLogger(__name__)


async def bot_link(bot: Bot, payload: str = "") -> str:
    me = await bot.me()
    return f"https://t.me/{me.username}" + (f"?start={payload}" if payload else "")


async def apply_start_payload(ctx: Services, user: User, payload: str) -> str | None:
    """/start parameter of a new player: ``ref_<id>`` is a referral, ``c_<id>`` is a card link, anything else is a source tag."""
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
                    crystals=User.crystals + settings.ref_bonus_invitee,
                )
            )
        if result.rowcount != 1 or not settings.ref_bonus_invitee:
            return None
        return texts.referral_welcome(settings.ref_bonus_invitee)

    if payload.startswith("c_"):
        tag = "card"
    else:
        tag = sanitize_tag(payload[4:] if payload.startswith("src_") else payload)
    if tag:
        async with ctx.db.begin() as s:
            await s.execute(update(User).where(User.id == user.id, User.source.is_(None)).values(source=tag))
    return None


async def reward_inviter(bot: Bot, ctx: Services, user: User) -> None:
    """Pay the inviter once the friend claims their first word (protection from fake accounts)."""
    if not user.referrer_id or user.referral_rewarded:
        return
    settings = ctx.settings
    bonus = settings.ref_bonus_inviter
    today = local_today(settings.tz)
    paid = False
    async with ctx.db.begin() as s:
        result = await s.execute(
            update(User).where(User.id == user.id, User.referral_rewarded.is_(False)).values(referral_rewarded=True)
        )
        if result.rowcount != 1:
            return
        if bonus:
            # не больше ref_daily_cap наград в день — фермы фейковых аккаунтов не окупаются
            same_day = User.ref_day == today
            rewarded = await s.execute(
                update(User)
                .where(
                    User.id == user.referrer_id,
                    or_(User.ref_day.is_(None), User.ref_day != today, User.ref_day_count < settings.ref_daily_cap),
                )
                .values(
                    crystals=User.crystals + bonus,
                    ref_earned=User.ref_earned + bonus,
                    ref_day=today,
                    ref_day_count=case((same_day, User.ref_day_count + 1), else_=1),
                )
            )
            paid = rewarded.rowcount == 1
    user.referral_rewarded = True
    if paid:
        await notify(bot, user.referrer_id, texts.referral_reward(bonus, user.first_name or "Друг"))


async def notify(bot: Bot, chat_id: int, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> bool:
    try:
        await bot.send_message(chat_id, text, reply_markup=reply_markup)
        return True
    except TelegramAPIError as e:
        log.info("Can't notify %s: %s", chat_id, e)
        return False


async def announce(
    bot: Bot, ctx: Services, text: str, photo: str | None = None, reply_markup: InlineKeyboardMarkup | None = None
) -> None:
    """Post to the "Chronicle of the World of Words" channel (if configured)."""
    channel = ctx.settings.news_channel
    if not channel:
        return
    try:
        if photo:
            await bot.send_photo(channel, photo, caption=text, reply_markup=reply_markup)
        else:
            await bot.send_message(channel, text, reply_markup=reply_markup)
    except TelegramAPIError as e:
        log.warning("News channel post failed: %s", e)


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
