"""Product analytics: a lightweight events table plus the numbers behind /stats."""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdView, BattleLog, Clan, Event, Payment, Task, User


def track(session: AsyncSession, name: str, user_id: int | None = None, **props) -> None:
    """Adds an event to the current transaction (committed with the caller's work)."""
    session.add(Event(user_id=user_id, name=name, props=props or None))


async def _count(session: AsyncSession, stmt) -> int:
    return int((await session.execute(stmt)).scalar_one() or 0)


async def stats(session: AsyncSession, now: datetime) -> dict:
    day, week, month = now - timedelta(days=1), now - timedelta(days=7), now - timedelta(days=30)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    users = select(func.count()).select_from(User)

    def revenue(since: datetime | None):
        stmt = select(func.coalesce(func.sum(Payment.stars), 0)).where(Payment.status == "paid")
        return stmt.where(Payment.created_at >= since) if since else stmt

    top_items = (
        await session.execute(
            select(Payment.item_id, func.sum(Payment.stars), func.count())
            .where(Payment.status == "paid", Payment.created_at >= week)
            .group_by(Payment.item_id)
            .order_by(func.sum(Payment.stars).desc())
            .limit(5)
        )
    ).all()
    return {
        "users_total": await _count(session, users),
        "users_new_today": await _count(session, users.where(User.created_at >= midnight)),
        "users_new_24h": await _count(session, users.where(User.created_at >= day)),
        "onboarded": await _count(session, users.where(User.city_id.is_not(None))),
        "dau": await _count(session, users.where(User.last_seen_at >= day)),
        "wau": await _count(session, users.where(User.last_seen_at >= week)),
        "mau": await _count(session, users.where(User.last_seen_at >= month)),
        "clans": await _count(
            session, select(func.count()).select_from(Clan).where(Clan.kind != "militia")
        ),
        "battles_24h": await _count(
            session, select(func.count()).select_from(BattleLog).where(BattleLog.created_at >= day)
        ),
        "stars_today": await _count(session, revenue(midnight)),
        "stars_7d": await _count(session, revenue(week)),
        "stars_30d": await _count(session, revenue(month)),
        "stars_total": await _count(session, revenue(None)),
        "ads_24h": await _count(
            session, select(func.count()).select_from(AdView).where(AdView.created_at >= day)
        ),
        "ads_7d": await _count(
            session, select(func.count()).select_from(AdView).where(AdView.created_at >= week)
        ),
        "tasks_active": await _count(
            session, select(func.count()).select_from(Task).where(Task.status == "active")
        ),
        "tasks_pending": await _count(
            session, select(func.count()).select_from(Task).where(Task.status == "pending")
        ),
        "suspects": await _count(
            session, users.where(User.suspicion >= 20, User.banned.is_(False))
        ),
        "banned": await _count(session, users.where(User.banned.is_(True))),
        "top_items_7d": [(item, int(stars), int(n)) for item, stars, n in top_items],
    }


def format_stats(s: dict) -> str:
    items = "\n".join(f"  • {i}: {stars} ⭐ ({n})" for i, stars, n in s["top_items_7d"]) or "  —"
    onboarded = round(100 * s["onboarded"] / s["users_total"]) if s["users_total"] else 0
    return (
        "📊 <b>Статистика</b>\n\n"
        f"👥 Игроков: {s['users_total']} (онбординг {onboarded}%)\n"
        f"🆕 Новых: сегодня {s['users_new_today']}, за 24 ч {s['users_new_24h']}\n"
        f"🔥 DAU / WAU / MAU: {s['dau']} / {s['wau']} / {s['mau']}\n"
        f"⚔️ Боёв за 24 ч: {s['battles_24h']} · кланов: {s['clans']}\n\n"
        f"⭐ Stars: сегодня {s['stars_today']}, 7 дн. {s['stars_7d']}, "
        f"30 дн. {s['stars_30d']}, всего {s['stars_total']}\n"
        f"Топ товаров за 7 дней:\n{items}\n\n"
        f"🎬 Реклама: 24 ч {s['ads_24h']}, 7 дн. {s['ads_7d']}\n"
        f"🎯 Задания: активных {s['tasks_active']}, на модерации {s['tasks_pending']}\n"
        f"🚨 Подозрительных: {s['suspects']} · забанено: {s['banned']}"
    )
