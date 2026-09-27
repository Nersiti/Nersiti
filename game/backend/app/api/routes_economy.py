from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_user_locked, limit
from app.db import get_session
from app.game import economy, player_service, referral_service
from app.game.cards import CARDS
from app.game.state import build_state
from app.models import User

router = APIRouter()


class TapIn(BaseModel):
    taps: int = Field(ge=0, le=10_000)


@router.post("/tap", dependencies=[Depends(limit("tap", 30, 10))])
async def tap(
    body: TapIn,
    user: User = Depends(get_user_locked),
    session: AsyncSession = Depends(get_session),
) -> dict:
    now = player_service.utcnow()
    level_before = user.level
    player_service.sync_user(user, now)
    earned = player_service.tap(user, body.taps, now)
    if user.level != level_before:
        await referral_service.check_level_bonus(session, user)
    state = await build_state(session, user, now)
    await session.commit()
    return {"earned": earned, "state": state}


@router.get("/upgrades")
async def upgrades(
    user: User = Depends(get_user_locked),
    session: AsyncSession = Depends(get_session),
) -> dict:
    now = player_service.utcnow()
    levels = await player_service.upgrade_levels(session, user.id)
    combo = await player_service.combo_status(session, user, now.date())
    await session.commit()
    return {"cards": [_card_dict(c, levels.get(c.id, 0)) for c in CARDS], "combo": combo}


@router.post("/upgrades/{card_id}/buy", dependencies=[Depends(limit("buy", 20, 10))])
async def buy_upgrade(
    card_id: str,
    user: User = Depends(get_user_locked),
    session: AsyncSession = Depends(get_session),
) -> dict:
    now = player_service.utcnow()
    player_service.sync_user(user, now)
    result = await player_service.buy_upgrade(session, user, card_id, now.date())
    levels = await player_service.upgrade_levels(session, user.id)
    combo = await player_service.combo_status(session, user, now.date())
    state = await build_state(session, user, now)
    await session.commit()
    card = next(c for c in CARDS if c.id == card_id)
    return {
        **result,
        "card": _card_dict(card, levels.get(card_id, 0)),
        "combo": combo,
        "state": state,
    }


@router.post("/daily/claim", dependencies=[Depends(limit("daily", 10, 60))])
async def claim_daily(
    user: User = Depends(get_user_locked),
    session: AsyncSession = Depends(get_session),
) -> dict:
    now = player_service.utcnow()
    player_service.sync_user(user, now)
    reward = player_service.claim_daily(user, now.date())
    state = await build_state(session, user, now)
    await session.commit()
    return {"reward": reward, "state": state}


def _card_dict(card, level: int) -> dict:
    maxed = level >= card.max_level
    return {
        "id": card.id,
        "category": card.category,
        "effect": card.effect,
        "level": level,
        "max_level": card.max_level,
        "next_cost": None if maxed else card.cost(level + 1),
        "next_gain": None if maxed else card.gain(level + 1),
        "total_effect": _total_effect(card, level),
        "battery_step": economy.BATTERY_ENERGY_PER_LEVEL if card.effect == "battery" else None,
    }


def _total_effect(card, level: int) -> int:
    return sum(card.gain(n) for n in range(1, level + 1))
