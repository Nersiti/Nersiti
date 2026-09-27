"""Rewarded ads (Adsgram). The reward is granted only by the ad network's server
callback, never by the client."""

import hmac
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.game import economy, player_service
from app.game.errors import GameError
from app.models import AdView, User, UserBoost
from app.redis_client import get_redis

REWARD_TYPES = ("energy", "passive", "attack")
INTENT_TTL_SECONDS = 15 * 60
AD_ATTACK_BOOST = "ad_attack"


def _count_key(user_id: int, now: datetime) -> str:
    return f"ads:count:{user_id}:{now:%Y%m%d}"


async def views_today(user_id: int, now: datetime) -> int:
    return int(await get_redis().get(_count_key(user_id, now)) or 0)


async def set_intent(user_id: int, reward_type: str, now: datetime) -> None:
    if reward_type not in REWARD_TYPES:
        raise GameError("bad_reward_type")
    if not get_settings().adsgram_block_id:
        raise GameError("ads_disabled", 404)
    if await views_today(user_id, now) >= economy.AD_DAILY_LIMIT:
        raise GameError("daily_limit", 409)
    await get_redis().set(f"ads:intent:{user_id}", reward_type, ex=INTENT_TTL_SECONDS)


def verify_secret(secret: str | None) -> bool:
    expected = get_settings().ads_callback_secret
    return bool(expected) and hmac.compare_digest(secret or "", expected)


async def grant_from_callback(session: AsyncSession, user: User, now: datetime) -> str | None:
    """User row must be locked. Returns the granted reward type, or None if over the limit."""
    redis = get_redis()
    count_key = _count_key(user.id, now)
    count = await redis.incr(count_key)
    if count == 1:
        await redis.expire(count_key, 2 * 86400)
    if count > economy.AD_DAILY_LIMIT:
        return None
    reward = await redis.getdel(f"ads:intent:{user.id}") or "energy"

    player_service.sync_user(user, now)
    if reward == "energy":
        user.energy = user.energy_max
        user.energy_updated_at = now
    elif reward == "passive":
        player_service.credit(user, economy.ad_passive_reward(user.income_per_hour))
    elif reward == "attack":
        boost = await session.get(UserBoost, (user.id, AD_ATTACK_BOOST), with_for_update=True)
        if boost is None:
            boost = UserBoost(user_id=user.id, boost_id=AD_ATTACK_BOOST, uses_today=0)
            session.add(boost)
        # One-shot boost for the next attack within an hour.
        boost.until = now + timedelta(hours=1)
    session.add(AdView(user_id=user.id, provider="adsgram", reward_type=reward, created_at=now))
    return reward
