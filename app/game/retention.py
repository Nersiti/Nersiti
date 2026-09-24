"""Retention: automatic reasons for a player to come back.

- «Месть»: the immunity of a captured word has ended — notify the former owner that they can take it back.
- The Lord status has ended — offer to renew it (only for those without auto-renewal).
- A player hasn't been around for a few days — gently remind them (no more than once a week).
- Weekly tournament: the top players by points earned during the week get crystals.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from sqlalchemy import func, or_, select, update

from app import keyboards as kb
from app import texts
from app.db import repo
from app.db.models import Card, User
from app.game.service import public_name
from app.services.growth import announce, notify
from app.utils import utcnow

if TYPE_CHECKING:
    from app.context import Services

log = logging.getLogger(__name__)

TOURNAMENT_WEEK = "tournament_week"
REMINDERS_INTERVAL = 3600.0  # проверять неактивных раз в час
REMINDERS_BATCH = 200


def week_key(ctx: Services) -> str:
    year, week, _ = datetime.now(ctx.settings.tz).isocalendar()
    return f"{year}-W{week:02d}"


async def notify_revenge(bot: Bot, ctx: Services) -> int:
    now = utcnow()
    async with ctx.db.session() as s:
        cards = (
            await s.scalars(
                select(Card)
                .where(
                    Card.revenge_to.is_not(None),
                    Card.status == "active",
                    or_(Card.protected_until.is_(None), Card.protected_until <= now),
                    or_(Card.shield_until.is_(None), Card.shield_until <= now),
                )
                .limit(100)
            )
        ).all()
    sent = 0
    for card in cards:
        target = card.revenge_to
        async with ctx.db.begin() as s:
            cleared = await s.execute(
                update(Card).where(Card.id == card.id, Card.revenge_to == target).values(revenge_to=None)
            )
        if cleared.rowcount == 1 and target and target != card.owner_id:
            if await notify(bot, target, texts.revenge_ready(card), kb.card_link_kb(card.id, "🏴 Отбить слово")):
                sent += 1
    return sent


async def notify_lord_expired(bot: Bot, ctx: Services) -> int:
    now = utcnow()
    async with ctx.db.session() as s:
        users = (
            await s.scalars(
                select(User)
                .where(
                    User.premium_until <= now,
                    User.premium_until > now - timedelta(days=3),
                    or_(User.lord_notice_until.is_(None), User.lord_notice_until != User.premium_until),
                    or_(User.sub_charge_id.is_(None), User.sub_canceled.is_(True)),
                    User.is_blocked.is_(False),
                )
                .limit(100)
            )
        ).all()
    sent = 0
    for user in users:
        async with ctx.db.begin() as s:
            await repo.set_fields(s, user.id, lord_notice_until=user.premium_until)
        if await notify(bot, user.id, texts.LORD_EXPIRED, kb.shop_link_kb()):
            sent += 1
    return sent


async def send_reminders(bot: Bot, ctx: Services) -> int:
    settings = ctx.settings
    if not settings.reminders_enabled:
        return 0
    now = utcnow()
    async with ctx.db.session() as s:
        users = (
            await s.scalars(
                select(User)
                .where(
                    User.last_seen_at < now - timedelta(days=settings.remind_after_days),
                    User.last_seen_at > now - timedelta(days=30),
                    User.is_blocked.is_(False),
                    User.is_banned.is_(False),
                    or_(User.reminded_at.is_(None), User.reminded_at < now - timedelta(days=settings.remind_every_days)),
                )
                .order_by(User.last_seen_at.desc())
                .limit(REMINDERS_BATCH)
            )
        ).all()
    if not users:
        return 0
    world = await ctx.game.world_size()
    auction = await ctx.auctions.current()
    sent = 0
    for user in users:
        async with ctx.db.begin() as s:
            await repo.set_fields(s, user.id, reminded_at=now)
            owned = await s.scalar(
                select(func.count(Card.id)).where(Card.owner_id == user.id, Card.status == "active")
            )
        text = texts.reminder(public_name(user), world, int(owned or 0), auction.display if auction else None)
        try:
            await bot.send_message(user.id, text)
            sent += 1
        except TelegramForbiddenError:
            async with ctx.db.begin() as s:
                await repo.set_fields(s, user.id, is_blocked=True)
        except Exception as e:  # noqa: BLE001 — одно сообщение не должно останавливать рассылку
            log.info("Reminder to %s failed: %s", user.id, e)
        await asyncio.sleep(0.05)
    return sent


@dataclass(frozen=True)
class Winner:
    user_id: int
    name: str
    points: int
    prize: int


async def run_tournament(bot: Bot, ctx: Services) -> list[Winner]:
    """At the start of a new week: prizes for the previous week's winners and a points reset."""
    if not ctx.settings.tournament_enabled:
        return []
    current = week_key(ctx)
    stored = await ctx.kv.get(TOURNAMENT_WEEK)
    if stored is None:
        await ctx.kv.set(TOURNAMENT_WEEK, current)
        return []
    if stored == current:
        return []
    prizes = [p for p in ctx.settings.tournament_prizes if p > 0]
    winners: list[Winner] = []
    async with ctx.db.begin() as s:
        if await repo.kv_get(s, TOURNAMENT_WEEK) != stored:  # уже подвели итоги
            return []
        top = (
            await s.scalars(
                select(User).where(User.week_points > 0).order_by(User.week_points.desc(), User.id).limit(len(prizes))
            )
        ).all()
        for user, prize in zip(top, prizes, strict=False):
            winners.append(Winner(user.id, public_name(user), user.week_points, prize))
            await s.execute(update(User).where(User.id == user.id).values(crystals=User.crystals + prize))
        await s.execute(update(User).where(User.week_points != 0).values(week_points=0))
        await repo.kv_set(s, TOURNAMENT_WEEK, current)
    ctx.kv.forget(TOURNAMENT_WEEK)
    for place, winner in enumerate(winners, 1):
        await notify(bot, winner.user_id, texts.tournament_prize(place, winner.prize, winner.points))
    if winners:
        await announce(bot, ctx, texts.news_tournament([(w.name, w.points, w.prize) for w in winners]))
    return winners


async def retention_tick(bot: Bot, ctx: Services) -> None:
    await notify_revenge(bot, ctx)
    await notify_lord_expired(bot, ctx)
    await run_tournament(bot, ctx)
    if time.monotonic() >= ctx.next_reminders_at:
        ctx.next_reminders_at = time.monotonic() + REMINDERS_INTERVAL
        await send_reminders(bot, ctx)
