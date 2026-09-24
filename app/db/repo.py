"""Database queries. Every balance change is an atomic UPDATE, so parallel updates never lose writes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram.types import User as TgUser
from sqlalchemy import case, delete, distinct, func, literal_column, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import Database
from app.db.models import Battle, Card, KeyValue, Payment, PromoCode, PromoUse, User
from app.utils import local_day_start_utc, utcnow

TOUCH_INTERVAL = 60  # секунд между обновлениями last_seen_at


# ---------- users ----------


async def get_or_create_user(db: Database, tg_user: TgUser, start_crystals: int) -> tuple[User, bool]:
    now = utcnow()
    first_name = (tg_user.first_name or "")[:128]
    username = tg_user.username[:64] if tg_user.username else None

    async with db.session() as s:
        user = await s.get(User, tg_user.id)
        if user is not None:
            stale = (now - user.last_seen_at).total_seconds() > TOUCH_INTERVAL
            if stale or user.is_blocked or user.username != username or user.first_name != first_name:
                await s.execute(
                    update(User)
                    .where(User.id == tg_user.id)
                    .values(username=username, first_name=first_name, last_seen_at=now, is_blocked=False)
                )
                await s.commit()
                user.username, user.first_name, user.last_seen_at, user.is_blocked = username, first_name, now, False
            return user, False

        user = User(
            id=tg_user.id,
            username=username,
            first_name=first_name,
            language_code=tg_user.language_code,
            created_at=now,
            last_seen_at=now,
            crystals=start_crystals,
        )
        s.add(user)
        try:
            await s.commit()
        except IntegrityError:
            await s.rollback()
            existing = await s.get(User, tg_user.id)
            assert existing is not None
            return existing, False
        return user, True


async def get_user(s: AsyncSession, user_id: int) -> User | None:
    return await s.get(User, user_id, populate_existing=True)


async def find_user(s: AsyncSession, query: str) -> User | None:
    query = query.strip()
    if query.lstrip("-").isdigit():
        return await get_user(s, int(query))
    username = query.lstrip("@")
    return await s.scalar(select(User).where(func.lower(User.username) == username.lower()))


async def set_fields(s: AsyncSession, user_id: int, **values: object) -> None:
    await s.execute(update(User).where(User.id == user_id).values(**values))


async def add_crystals(s: AsyncSession, user_id: int, amount: int) -> None:
    """Add (or remove, if negative) crystals; balance never drops below zero."""
    new_value = User.crystals + amount
    await s.execute(
        update(User).where(User.id == user_id).values(crystals=case((new_value < 0, 0), else_=new_value))
    )


async def extend_premium(
    s: AsyncSession, user_id: int, days: int, now: datetime, at_least: datetime | None = None
) -> datetime:
    current = await s.scalar(select(User.premium_until).where(User.id == user_id))
    base = current if current and current > now else now
    until = base + timedelta(days=days)
    if at_least and at_least > until:
        until = at_least
    await s.execute(update(User).where(User.id == user_id).values(premium_until=until))
    return until


async def count_referrals(s: AsyncSession, user_id: int) -> int:
    return int(await s.scalar(select(func.count()).select_from(User).where(User.referrer_id == user_id)) or 0)


# ---------- promo codes ----------


async def create_promo(
    s: AsyncSession, code: str, crystals: int, max_uses: int, premium_days: int, expires_at: datetime | None
) -> None:
    s.add(
        PromoCode(
            code=code.upper(),
            crystals=crystals,
            premium_days=premium_days,
            max_uses=max_uses,
            used=0,
            expires_at=expires_at,
            created_at=utcnow(),
        )
    )
    await s.flush()


async def list_promos(s: AsyncSession, limit: int = 20) -> list[PromoCode]:
    return list((await s.scalars(select(PromoCode).order_by(PromoCode.created_at.desc()).limit(limit))).all())


async def activate_promo(s: AsyncSession, code: str, user_id: int) -> PromoCode | str:
    """Returns the promo code on success or an error key: not_found | expired | used | exhausted."""
    now = utcnow()
    code = code.upper()
    promo = await s.get(PromoCode, code, populate_existing=True)
    if promo is None:
        return "not_found"
    if promo.expires_at and promo.expires_at < now:
        return "expired"
    already = await s.scalar(select(PromoUse.id).where(PromoUse.code == code, PromoUse.user_id == user_id))
    if already:
        return "used"
    result = await s.execute(
        update(PromoCode)
        .where(PromoCode.code == code, (PromoCode.max_uses == 0) | (PromoCode.used < PromoCode.max_uses))
        .values(used=PromoCode.used + 1)
    )
    if result.rowcount != 1:
        return "exhausted"
    s.add(PromoUse(code=code, user_id=user_id, created_at=now))
    await s.flush()
    if promo.crystals:
        await add_crystals(s, user_id, promo.crystals)
    if promo.premium_days:
        await extend_premium(s, user_id, promo.premium_days, now)
    return promo


# ---------- key-value settings ----------


async def kv_get(s: AsyncSession, key: str) -> str | None:
    row = await s.get(KeyValue, key, populate_existing=True)
    return row.value if row else None


async def kv_set(s: AsyncSession, key: str, value: str | None) -> None:
    await s.execute(delete(KeyValue).where(KeyValue.key == key))
    if value is not None:
        s.add(KeyValue(key=key, value=value))
        await s.flush()


# ---------- statistics ----------


@dataclass
class Stats:
    users_total: int
    users_today: int
    active_today: int
    active_week: int
    premium_active: int
    blocked: int
    cards_total: int
    cards_today: int
    battles_today: int
    crystals_total: int
    payments_today: int
    stars_today: int
    rub_today: int
    payers_total: int
    stars_total: int
    rub_total: int


async def collect_stats(s: AsyncSession, tz: ZoneInfo) -> Stats:
    now = utcnow()
    day_start = local_day_start_utc(tz)
    week_start = local_day_start_utc(tz, days_ago=6)

    async def count(stmt: object) -> int:
        return int(await s.scalar(stmt) or 0)  # type: ignore[arg-type]

    users = select(func.count()).select_from(User)
    ok_payments = Payment.status == "succeeded"
    rub_providers = Payment.provider.in_(("tg_rub", "yookassa"))

    return Stats(
        users_total=await count(users),
        users_today=await count(users.where(User.created_at >= day_start)),
        active_today=await count(users.where(User.last_seen_at >= day_start)),
        active_week=await count(users.where(User.last_seen_at >= week_start)),
        premium_active=await count(users.where(User.premium_until > now)),
        blocked=await count(users.where(User.is_blocked.is_(True))),
        cards_total=await count(select(func.count(Card.id)).where(Card.status == "active")),
        cards_today=await count(
            select(func.count(Card.id)).where(Card.status == "active", Card.created_at >= day_start)
        ),
        battles_today=await count(select(func.count(Battle.id)).where(Battle.created_at >= day_start)),
        crystals_total=await count(select(func.sum(User.crystals))),
        payments_today=await count(
            select(func.count()).select_from(Payment).where(ok_payments, Payment.paid_at >= day_start)
        ),
        stars_today=await count(
            select(func.sum(Payment.amount)).where(
                ok_payments, Payment.provider == "stars", Payment.paid_at >= day_start
            )
        ),
        rub_today=await count(
            select(func.sum(Payment.amount)).where(ok_payments, rub_providers, Payment.paid_at >= day_start)
        ),
        payers_total=await count(select(func.count(distinct(Payment.user_id))).where(ok_payments)),
        stars_total=await count(select(func.sum(Payment.amount)).where(ok_payments, Payment.provider == "stars")),
        rub_total=await count(select(func.sum(Payment.amount)).where(ok_payments, rub_providers)),
    )


@dataclass
class SourceRow:
    source: str
    users: int
    payers: int
    stars: int
    rub: int


async def source_stats(s: AsyncSession, limit: int = 30) -> list[SourceRow]:
    # literal_column: одинаковый текст выражения в SELECT и GROUP BY (важно для PostgreSQL)
    source = func.coalesce(User.source, literal_column("'organic'"))
    users_q = (
        select(source.label("src"), func.count(User.id))
        .group_by(source)
        .order_by(func.count(User.id).desc())
        .limit(limit)
    )
    rows = (await s.execute(users_q)).all()

    pay_q = (
        select(
            source.label("src"),
            func.count(distinct(Payment.user_id)),
            func.coalesce(func.sum(case((Payment.provider == "stars", Payment.amount), else_=0)), 0),
            func.coalesce(func.sum(case((Payment.provider != "stars", Payment.amount), else_=0)), 0),
        )
        .select_from(Payment)
        .join(User, User.id == Payment.user_id)
        .where(Payment.status == "succeeded")
        .group_by(source)
    )
    payments = {row[0]: row[1:] for row in (await s.execute(pay_q)).all()}

    result = []
    for src, users_count in rows:
        payers, stars, rub = payments.get(src, (0, 0, 0))
        result.append(SourceRow(src, int(users_count), int(payers), int(stars), int(rub)))
    return result


async def user_payments_summary(s: AsyncSession, user_id: int) -> tuple[int, int, int]:
    """(количество платежей, звёзд, копеек)"""
    row = (
        await s.execute(
            select(
                func.count(Payment.id),
                func.coalesce(func.sum(case((Payment.provider == "stars", Payment.amount), else_=0)), 0),
                func.coalesce(func.sum(case((Payment.provider != "stars", Payment.amount), else_=0)), 0),
            ).where(Payment.user_id == user_id, Payment.status == "succeeded")
        )
    ).one()
    return int(row[0]), int(row[1]), int(row[2])
