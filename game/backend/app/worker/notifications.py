"""Notification sender and the jobs that produce notifications."""

import asyncio
import html
import json
import logging
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_sessionmaker
from app.game import clan_service, economy, world_service
from app.i18n import pick_lang, t
from app.models import BattleLog, City, Clan, User
from app.notify import QUEUE_KEY, enqueue, url_button, webapp_button
from app.redis_client import get_redis

log = logging.getLogger("worker.notify")

GLOBAL_RATE_PER_SEC = 25
PER_CHAT_INTERVAL_SEC = 1.0
LOSS_WINDOW = timedelta(minutes=30)
DIGEST_WINDOW = timedelta(hours=3)
ACTIVE_MEMBER_WINDOW = timedelta(hours=24)
MAX_CITIES_IN_TEXT = 3


def _markup(button: dict | None) -> InlineKeyboardMarkup | None:
    if not button:
        return None
    if "web_app" in button:
        btn = InlineKeyboardButton(text=button["text"], web_app=WebAppInfo(url=button["web_app"]))
    else:
        btn = InlineKeyboardButton(text=button["text"], url=button["url"])
    return InlineKeyboardMarkup(inline_keyboard=[[btn]])


class Sender:
    """Drains the Redis queue respecting Telegram limits."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.last_sent: dict[int, float] = {}

    async def process(self, raw: str) -> str:
        item = json.loads(raw)
        try:
            await self.bot.send_message(
                chat_id=item["chat_id"],
                text=item["text"],
                reply_markup=_markup(item.get("button")),
                disable_web_page_preview=True,
            )
        except TelegramRetryAfter as exc:
            log.warning("flood control: retry after %ss", exc.retry_after)
            await asyncio.sleep(exc.retry_after)
            await get_redis().lpush(QUEUE_KEY, raw)
            return "retry"
        except TelegramForbiddenError:
            if item.get("user_id"):
                async with get_sessionmaker()() as session:
                    await session.execute(
                        update(User).where(User.id == item["user_id"]).values(notify_enabled=False)
                    )
                    await session.commit()
            return "blocked"
        except TelegramAPIError as exc:
            log.info("notification to %s failed: %s", item["chat_id"], exc)
            return "failed"
        self.last_sent[item["chat_id"]] = time.monotonic()
        return "sent"

    async def run(self, stop: asyncio.Event) -> None:
        redis = get_redis()
        while not stop.is_set():
            popped = await redis.blpop([QUEUE_KEY], timeout=1)
            if not popped:
                continue
            raw = popped[1]
            chat_id = json.loads(raw)["chat_id"]
            wait = PER_CHAT_INTERVAL_SEC - (time.monotonic() - self.last_sent.get(chat_id, 0))
            if wait > 0:
                await redis.rpush(QUEUE_KEY, raw)
                await asyncio.sleep(min(wait, 0.05))
                continue
            await self.process(raw)
            await asyncio.sleep(1 / GLOBAL_RATE_PER_SEC)


def _cities_text(city_ids: list[int], cities: dict[int, City], lang: str) -> str:
    names = [html.escape(world_service.city_name(cities[c], lang)) for c in city_ids if c in cities]
    text = ", ".join(names[:MAX_CITIES_IN_TEXT])
    return f"{text}…" if len(names) > MAX_CITIES_IN_TEXT else text


async def _window_start(key: str, now: datetime, default: timedelta) -> datetime:
    redis = get_redis()
    raw = await redis.get(key)
    await redis.set(key, now.isoformat())
    return datetime.fromisoformat(raw) if raw else now - default


async def sector_loss_summary(session: AsyncSession, now: datetime) -> int:
    """Every 30 minutes: tells players whose sectors were captured, and active members
    of clans that lost sectors. Returns the number of queued messages."""
    since = await _window_start("notify:losses:since", now, LOSS_WINDOW)
    flips = (
        (
            await session.execute(
                select(BattleLog).where(
                    BattleLog.flipped.is_(True),
                    BattleLog.prev_owner_clan_id.is_not(None),
                    BattleLog.created_at > since,
                    BattleLog.created_at <= now,
                )
            )
        )
        .scalars()
        .all()
    )
    if not flips:
        return 0

    city_ids = {f.city_id for f in flips}
    cities = {
        c.id: c
        for c in (await session.execute(select(City).where(City.id.in_(city_ids)))).scalars()
    }
    clan_ids = {f.clan_id for f in flips} | {f.prev_owner_clan_id for f in flips}
    clans = {
        c.id: c
        for c in (await session.execute(select(Clan).where(Clan.id.in_(clan_ids)))).scalars()
    }

    by_actor: dict[int, list[BattleLog]] = defaultdict(list)
    by_clan: dict[int, list[BattleLog]] = defaultdict(list)
    for f in flips:
        if f.prev_actor_id and f.prev_actor_id != f.user_id:
            by_actor[f.prev_actor_id].append(f)
        by_clan[f.prev_owner_clan_id].append(f)

    active = (
        await session.execute(
            select(BattleLog.user_id, BattleLog.clan_id)
            .where(
                BattleLog.clan_id.in_(by_clan.keys()),
                BattleLog.created_at > now - ACTIVE_MEMBER_WINDOW,
            )
            .distinct()
        )
    ).all()
    recipients = set(by_actor) | {uid for uid, _ in active}
    users = {
        u.id: u
        for u in (
            await session.execute(
                select(User).where(
                    User.id.in_(recipients), User.notify_enabled.is_(True), User.banned.is_(False)
                )
            )
        ).scalars()
    }

    queued = 0
    notified: set[int] = set()
    for actor_id, lost in by_actor.items():
        user = users.get(actor_id)
        if user is None:
            continue
        lang = pick_lang(user.language_code)
        enemy_id = Counter(f.clan_id for f in lost).most_common(1)[0][0]
        enemy = clans.get(enemy_id)
        text = t(
            lang,
            "notify.lost",
            n=len(lost),
            cities=_cities_text(list(dict.fromkeys(f.city_id for f in lost)), cities, lang),
            clan=html.escape(
                await clan_service.display_title(session, enemy, lang) if enemy else "?"
            ),
        )
        if await enqueue(
            user.id, text, button=webapp_button(t(lang, "notify.button")), user_id=user.id, now=now
        ):
            queued += 1
        notified.add(user.id)

    for user_id, clan_id in active:
        user = users.get(user_id)
        if user is None or user.id in notified or user.clan_id != clan_id:
            continue
        lost = by_clan.get(clan_id, [])
        clan = clans.get(clan_id)
        if not lost or clan is None:
            continue
        lang = pick_lang(user.language_code)
        text = t(
            lang,
            "notify.clan_losses",
            clan=html.escape(await clan_service.display_title(session, clan, lang)),
            n=len(lost),
            cities=_cities_text(list(dict.fromkeys(f.city_id for f in lost)), cities, lang),
        )
        if await enqueue(
            user.id, text, button=webapp_button(t(lang, "notify.button")), user_id=user.id, now=now
        ):
            queued += 1
        notified.add(user.id)
    return queued


async def group_digests(session: AsyncSession, now: datetime) -> int:
    """Every 3 hours: a short report in each group clan's chat if anything happened."""
    since = now - DIGEST_WINDOW
    won = dict(
        (
            await session.execute(
                select(BattleLog.clan_id, func.count())
                .where(BattleLog.flipped.is_(True), BattleLog.created_at > since)
                .group_by(BattleLog.clan_id)
            )
        ).all()
    )
    lost = dict(
        (
            await session.execute(
                select(BattleLog.prev_owner_clan_id, func.count())
                .where(
                    BattleLog.flipped.is_(True),
                    BattleLog.prev_owner_clan_id.is_not(None),
                    BattleLog.created_at > since,
                )
                .group_by(BattleLog.prev_owner_clan_id)
            )
        ).all()
    )
    active_ids = set(won) | set(lost)
    if not active_ids:
        return 0
    clans = (
        (
            await session.execute(
                select(Clan).where(
                    Clan.id.in_(active_ids),
                    Clan.kind == clan_service.GROUP,
                    Clan.tg_chat_id.is_not(None),
                    Clan.banned.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    queued = 0
    bot_username = get_settings().bot_username
    for clan in clans:
        owner = await session.get(User, clan.owner_user_id) if clan.owner_user_id else None
        lang = pick_lang(owner.language_code if owner else "ru")
        text = t(
            lang,
            "notify.digest",
            clan=html.escape(clan.title),
            won=won.get(clan.id, 0),
            lost=lost.get(clan.id, 0),
            held=await clan_service.sectors_held(session, clan.id),
            rank=await clan_service.clan_rank(session, clan),
        )
        link = clan_service.start_link(bot_username, clan.id)
        await enqueue(
            clan.tg_chat_id, text, button=url_button(t(lang, "notify.digest.button"), link)
        )
        queued += 1
    return queued


async def storage_full_reminders(session: AsyncSession, now: datetime) -> int:
    """Hourly: players whose offline storage just filled up get one reminder per day."""
    base_cap = timedelta(hours=economy.OFFLINE_CAP_HOURS)
    ext_cap = timedelta(hours=economy.OFFLINE_CAP_HOURS_EXTENDED)
    extended = or_(
        and_(User.vip_until.is_not(None), User.vip_until > now),
        and_(User.offline_cap_until.is_not(None), User.offline_cap_until > now),
    )
    users = (
        (
            await session.execute(
                select(User).where(
                    User.income_per_hour > 0,
                    User.notify_enabled.is_(True),
                    User.banned.is_(False),
                    or_(
                        and_(
                            ~extended,
                            User.last_seen_at <= now - base_cap,
                            User.last_seen_at > now - base_cap - timedelta(hours=1),
                        ),
                        and_(
                            extended,
                            User.last_seen_at <= now - ext_cap,
                            User.last_seen_at > now - ext_cap - timedelta(hours=1),
                        ),
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    redis = get_redis()
    queued = 0
    for user in users:
        if not await redis.set(
            f"notify:storage:{user.id}:{now:%Y%m%d}", "1", ex=2 * 86400, nx=True
        ):
            continue
        vip = user.vip_until is not None and user.vip_until > now
        cap_hours = economy.offline_cap_hours(
            vip, user.offline_cap_until is not None and user.offline_cap_until > now
        )
        coins = int(economy.effective_income(user.income_per_hour, vip) * cap_hours)
        lang = pick_lang(user.language_code)
        text = t(lang, "notify.storage_full", coins=f"{coins:,}".replace(",", " "))
        if await enqueue(
            user.id, text, button=webapp_button(t(lang, "notify.button")), user_id=user.id, now=now
        ):
            queued += 1
    return queued


async def weekly_group_results(session: AsyncSession, now: datetime) -> int:
    """Mondays: a weekly summary with the clan's best fighter in group clan chats."""
    since = now - timedelta(days=7)
    clans = (
        (
            await session.execute(
                select(Clan).where(
                    Clan.kind == clan_service.GROUP,
                    Clan.tg_chat_id.is_not(None),
                    Clan.banned.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    queued = 0
    bot_username = get_settings().bot_username
    for clan in clans:
        won = (
            await session.execute(
                select(func.count())
                .select_from(BattleLog)
                .where(
                    BattleLog.clan_id == clan.id,
                    BattleLog.flipped.is_(True),
                    BattleLog.created_at > since,
                )
            )
        ).scalar_one()
        lost = (
            await session.execute(
                select(func.count())
                .select_from(BattleLog)
                .where(
                    BattleLog.prev_owner_clan_id == clan.id,
                    BattleLog.flipped.is_(True),
                    BattleLog.created_at > since,
                )
            )
        ).scalar_one()
        if won == 0 and lost == 0:
            continue
        best = (
            await session.execute(
                select(User.first_name, func.sum(BattleLog.power).label("power"))
                .join(User, User.id == BattleLog.user_id)
                .where(BattleLog.clan_id == clan.id, BattleLog.created_at > since)
                .group_by(User.id, User.first_name)
                .order_by(func.sum(BattleLog.power).desc())
                .limit(1)
            )
        ).first()
        owner = await session.get(User, clan.owner_user_id) if clan.owner_user_id else None
        lang = pick_lang(owner.language_code if owner else "ru")
        text = t(
            lang,
            "notify.weekly",
            clan=html.escape(clan.title),
            won=won,
            lost=lost,
            held=await clan_service.sectors_held(session, clan.id),
            rank=await clan_service.clan_rank(session, clan),
            best=html.escape(best.first_name) if best else "—",
        )
        link = clan_service.start_link(bot_username, clan.id)
        await enqueue(
            clan.tg_chat_id, text, button=url_button(t(lang, "notify.digest.button"), link)
        )
        queued += 1
    return queued
