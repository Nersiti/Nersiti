"""Serializes the player's state for the Mini App."""

import time
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.game import clan_service, economy, world_service
from app.game.player_service import has_autocollector, is_vip
from app.i18n import pick_lang
from app.models import City, Clan, User


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


# Per-process caches: every request returns the full state, and cities never change
# while clan summaries may lag a few seconds. This saves two queries per request.
_CITY_TTL = 300.0
_CLAN_TTL = 10.0
_city_cache: dict[tuple[int, str], tuple[float, dict]] = {}
_clan_cache: dict[tuple[int, str], tuple[float, dict]] = {}


def reset_caches() -> None:
    _city_cache.clear()
    _clan_cache.clear()


async def _city_info(session: AsyncSession, city_id: int, lang: str) -> dict | None:
    key = (city_id, lang)
    hit = _city_cache.get(key)
    if hit and time.monotonic() - hit[0] < _CITY_TTL:
        return hit[1]
    city = await session.get(City, city_id)
    if city is None:
        return None
    info = world_service.city_to_dict(city, lang)
    _city_cache[key] = (time.monotonic(), info)
    return info


async def _clan_info(session: AsyncSession, clan_id: int, lang: str) -> dict | None:
    key = (clan_id, lang)
    hit = _clan_cache.get(key)
    if hit and time.monotonic() - hit[0] < _CLAN_TTL:
        return hit[1]
    clan = await session.get(Clan, clan_id)
    if clan is None:
        return None
    info = await clan_service.clan_summary(session, clan, lang)
    _clan_cache[key] = (time.monotonic(), info)
    return info


async def build_state(session: AsyncSession, user: User, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    lang = pick_lang(user.language_code)
    city = await _city_info(session, user.city_id, lang) if user.city_id else None
    clan = await _clan_info(session, user.clan_id, lang) if user.clan_id else None
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
        "city": city,
        "clan": clan,
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
        "ads_block_id": settings.adsgram_block_id or None,
    }
