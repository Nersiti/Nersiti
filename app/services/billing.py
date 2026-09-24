"""Limits and charging: daily free quota -> Premium quota -> credits."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sqlalchemy import case, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import Usage, User
from app.utils import local_today, utcnow


class Kind(StrEnum):
    CHAT = "chat"
    IMAGE = "image"


@dataclass(frozen=True)
class Charge:
    ok: bool
    kind: Kind
    source: str = ""  # free | premium | credits
    cost: int = 0  # сколько кредитов списано
    remaining: int | None = None  # остаток дневного лимита (для free/premium)
    premium: bool = False


def is_premium(user: User, now: datetime | None = None) -> bool:
    return bool(user.premium_until and user.premium_until > (now or utcnow()))


def daily_limit(settings: Settings, kind: Kind, premium: bool) -> int:
    if kind is Kind.CHAT:
        return settings.premium_chat_per_day if premium else settings.free_chat_per_day
    return settings.premium_images_per_day if premium else settings.free_images_per_day


def cost_of(settings: Settings, kind: Kind) -> int:
    return settings.chat_cost if kind is Kind.CHAT else settings.image_cost


def used_today(user: User, settings: Settings) -> tuple[int, int]:
    if user.counters_date != local_today(settings.tz):
        return 0, 0
    return user.chat_today or 0, user.images_today or 0


def _counter(kind: Kind):  # type: ignore[no-untyped-def]
    return User.chat_today if kind is Kind.CHAT else User.images_today


async def charge(s: AsyncSession, user_id: int, kind: Kind, settings: Settings) -> Charge:
    now = utcnow()
    today = local_today(settings.tz)
    await s.execute(
        update(User)
        .where(User.id == user_id, or_(User.counters_date.is_(None), User.counters_date != today))
        .values(chat_today=0, images_today=0, counters_date=today)
    )
    premium_until = await s.scalar(select(User.premium_until).where(User.id == user_id))
    premium = bool(premium_until and premium_until > now)
    limit = daily_limit(settings, kind, premium)
    counter = _counter(kind)

    result = await s.execute(
        update(User).where(User.id == user_id, counter < limit).values({counter: counter + 1})
    )
    if result.rowcount == 1:
        used = int(await s.scalar(select(counter).where(User.id == user_id)) or 0)
        return Charge(
            ok=True,
            kind=kind,
            source="premium" if premium else "free",
            remaining=max(limit - used, 0),
            premium=premium,
        )

    cost = cost_of(settings, kind)
    result = await s.execute(
        update(User).where(User.id == user_id, User.credits >= cost).values(credits=User.credits - cost)
    )
    if result.rowcount == 1:
        return Charge(ok=True, kind=kind, source="credits", cost=cost, premium=premium)
    return Charge(ok=False, kind=kind, cost=cost, premium=premium)


async def refund(s: AsyncSession, user_id: int, ch: Charge) -> None:
    """Return what was charged when generation failed."""
    if not ch.ok:
        return
    if ch.source == "credits":
        await s.execute(update(User).where(User.id == user_id).values(credits=User.credits + ch.cost))
        return
    counter = _counter(ch.kind)
    await s.execute(
        update(User).where(User.id == user_id).values({counter: case((counter > 0, counter - 1), else_=0)})
    )


async def record_usage(s: AsyncSession, user_id: int, ch: Charge) -> None:
    total = User.total_chat if ch.kind is Kind.CHAT else User.total_images
    await s.execute(update(User).where(User.id == user_id).values({total: total + 1}))
    s.add(Usage(user_id=user_id, kind=ch.kind.value, source=ch.source, cost=ch.cost, created_at=utcnow()))
