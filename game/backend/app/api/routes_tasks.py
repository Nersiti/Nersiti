from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_user, get_user_locked, limit
from app.config import get_settings
from app.db import get_session
from app.game import ads_service, economy, player_service, referral_service, tasks_service
from app.game.errors import GameError
from app.game.state import build_state
from app.i18n import pick_lang
from app.models import User

router = APIRouter()


@router.get("/tasks")
async def tasks(
    user: User = Depends(get_user), session: AsyncSession = Depends(get_session)
) -> dict:
    now = player_service.utcnow()
    lang = pick_lang(user.language_code)
    return {
        "tasks": await tasks_service.list_tasks(session, user, lang, now),
        "ads": {
            "enabled": bool(get_settings().adsgram_block_id),
            "block_id": get_settings().adsgram_block_id or None,
            "views_today": await ads_service.views_today(user.id, now),
            "daily_limit": economy.AD_DAILY_LIMIT,
            "passive_reward": economy.ad_passive_reward(user.income_per_hour),
        },
    }


@router.post("/tasks/{task_id}/check", dependencies=[Depends(limit("task_check", 20, 60))])
async def check_task(
    task_id: int,
    user: User = Depends(get_user_locked),
    session: AsyncSession = Depends(get_session),
) -> dict:
    now = player_service.utcnow()
    player_service.sync_user(user, now)
    reward = await tasks_service.check_task(session, user, task_id, now)
    state = await build_state(session, user, now)
    await session.commit()
    return {"reward": reward, "state": state}


@router.get("/referrals")
async def referrals(
    user: User = Depends(get_user), session: AsyncSession = Depends(get_session)
) -> dict:
    return await referral_service.summary(session, user, player_service.utcnow())


@router.post("/referrals/claim", dependencies=[Depends(limit("ref_claim", 10, 60))])
async def claim_referrals(
    user: User = Depends(get_user_locked),
    session: AsyncSession = Depends(get_session),
) -> dict:
    now = player_service.utcnow()
    player_service.sync_user(user, now)
    reward = await referral_service.claim_mentor_bonus(session, user, now)
    state = await build_state(session, user, now)
    await session.commit()
    return {"reward": reward, "state": state}


class AdIntentIn(BaseModel):
    reward_type: str = Field(max_length=16)


@router.post("/ads/intent", dependencies=[Depends(limit("ad_intent", 30, 60))])
async def ad_intent(body: AdIntentIn, user: User = Depends(get_user)) -> dict:
    await ads_service.set_intent(user.id, body.reward_type, player_service.utcnow())
    return {"block_id": get_settings().adsgram_block_id}


@router.get("/ads/callback")
async def ad_callback(
    userid: int = Query(),
    secret: str | None = Query(default=None, max_length=200),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Server-to-server reward callback configured in the Adsgram dashboard:
    https://<domain>/api/ads/callback?userid=[userId]&secret=<ADS_CALLBACK_SECRET>"""
    if not ads_service.verify_secret(secret):
        raise GameError("forbidden", 403)
    user = await session.get(User, userid, with_for_update=True)
    if user is None or user.banned:
        return {"ok": False}
    reward = await ads_service.grant_from_callback(session, user, player_service.utcnow())
    await session.commit()
    return {"ok": reward is not None, "reward": reward}
