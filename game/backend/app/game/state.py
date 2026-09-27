"""Serializes the player's state for the Mini App."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.game import clan_service, economy, world_service
from app.game.player_service import has_autocollector, is_vip
from app.i18n import pick_lang
from app.models import City, Clan, User


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


async def build_state(session: AsyncSession, user: User, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    lang = pick_lang(user.language_code)
    city = await session.get(City, user.city_id) if user.city_id else None
    clan = await session.get(Clan, user.clan_id) if user.clan_id else None
    vip = is_vip(user, now)
    level_from, level_to = economy.level_bounds(user.level)
    today = now.date()
    claimed_today = user.daily_last_date == today
    if claimed_today:
        next_daily_day = user.daily_streak + 1
    elif user.daily_last_date == today - timedelta(days=1):
        next_daily_day = user.daily_streak + 1
    else:
        next_daily_day = 1

    return {
        "user": {
            "id": user.id,
            "first_name": user.first_name,
            "username": user.username,
            "photo_url": user.photo_url,
            "lang": lang,
            "is_premium": user.is_premium,
        },
        "onboarded": city is not None,
        "country_code": user.country_code,
        "country_name": (
            world_service.country_name(user.country_code, lang) if user.country_code else None
        ),
        "city": world_service.city_to_dict(city, lang) if city else None,
        "clan": await clan_service.clan_summary(session, clan, lang) if clan else None,
        "clan_joined_at": _iso(user.clan_joined_at),
        "coins": user.coins,
        "total_earned": user.total_earned,
        "level": user.level,
        "level_from": level_from,
        "level_to": level_to,
        "energy": user.energy,
        "energy_max": user.energy_max,
        "energy_regen_per_sec": economy.ENERGY_REGEN_PER_SEC,
        "tap_power": economy.tap_power(user.level, user.multitap_level),
        "income_per_hour": round(economy.effective_income(user.income_per_hour, vip)),
        "offline_cap_hours": economy.offline_cap_hours(vip, has_autocollector(user, now)),
        "attack_mult": economy.bp_to_mult(user.attack_bonus_bp),
        "defense_mult": economy.bp_to_mult(user.defense_bonus_bp),
        "vip_until": _iso(user.vip_until) if vip else None,
        "notify_enabled": user.notify_enabled,
        "daily": {
            "streak": user.daily_streak,
            "claimed_today": claimed_today,
            "next_day": min(next_daily_day, len(economy.DAILY_REWARDS)),
            "next_reward": economy.daily_reward(next_daily_day),
            "rewards": economy.DAILY_REWARDS,
        },
        "server_time": now.isoformat(),
    }


def build_config() -> dict:
    settings = get_settings()
    return {
        "game_name": settings.game_name,
        "bot_username": settings.bot_username,
        "max_taps_per_sec": economy.MAX_TAPS_PER_SEC,
    }
