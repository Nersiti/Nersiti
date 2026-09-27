from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_identity, limit
from app.auth import TgIdentity
from app.db import get_session
from app.game import clan_service, player_service
from app.game.state import build_config, build_state
from app.i18n import pick_lang
from app.models import Clan

router = APIRouter()


class SessionIn(BaseModel):
    # Fallback for ?sp= when the app was opened from the bot chat button.
    start_param: str | None = Field(default=None, max_length=64)


@router.post("/session", dependencies=[Depends(limit("session", 30, 60))])
async def create_session(
    body: SessionIn,
    identity: TgIdentity = Depends(get_identity),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if identity.start_param is None and body.start_param:
        # initData signature does not cover ?sp=, but it only carries a referral/clan hint.
        start_param = body.start_param
    else:
        start_param = identity.start_param
    user, created = await player_service.upsert_user(session, identity, start_param)
    if user.banned:
        await session.commit()
        raise HTTPException(status_code=403, detail="banned")
    now = player_service.utcnow()
    offline_earned = player_service.sync_user(user, now)
    await clan_service.recheck_subscription(session, user, now)

    invite_clan = None
    invite_id = clan_service.parse_clan_param(start_param)
    if invite_id is not None and invite_id != user.clan_id:
        clan = await session.get(Clan, invite_id)
        if clan is not None and not clan.banned and clan.kind != clan_service.MILITIA:
            invite_clan = await clan_service.clan_summary(
                session, clan, pick_lang(user.language_code)
            )

    state = await build_state(session, user, now)
    await session.commit()
    return {
        "created": created,
        "offline_earned": offline_earned,
        "invite_clan": invite_clan,
        "state": state,
        "config": build_config(),
    }
