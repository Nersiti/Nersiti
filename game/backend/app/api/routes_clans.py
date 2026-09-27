from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_user, get_user_locked, limit
from app.config import get_settings
from app.db import get_session
from app.game import clan_service, player_service
from app.game.errors import GameError
from app.game.state import build_state
from app.i18n import pick_lang
from app.models import Clan, User

router = APIRouter()


@router.get("/clans/top")
async def top_clans(
    limit_: int = Query(default=50, ge=1, le=100, alias="limit"),
    user: User = Depends(get_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    lang = pick_lang(user.language_code)
    clans = (
        (
            await session.execute(
                select(Clan)
                .where(Clan.banned.is_(False), Clan.members_count > 0)
                .order_by(Clan.season_points.desc(), Clan.members_count.desc(), Clan.id)
                .limit(limit_)
            )
        )
        .scalars()
        .all()
    )
    promoted = (
        (
            await session.execute(
                select(Clan)
                .where(Clan.banned.is_(False), Clan.promoted_until > player_service.utcnow())
                .order_by(Clan.promoted_until.desc())
                .limit(5)
            )
        )
        .scalars()
        .all()
    )
    return {
        "items": [await clan_service.clan_summary(session, c, lang) for c in clans],
        "promoted": [await clan_service.clan_summary(session, c, lang) for c in promoted],
    }


@router.get("/clans/{clan_id}")
async def clan_details(
    clan_id: int,
    user: User = Depends(get_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    clan = await session.get(Clan, clan_id)
    if clan is None or clan.banned:
        raise GameError("clan_not_found", 404)
    lang = pick_lang(user.language_code)
    members = (
        (
            await session.execute(
                select(User)
                .where(User.clan_id == clan.id, User.banned.is_(False))
                .order_by(User.season_score.desc(), User.id)
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    return {
        **await clan_service.clan_summary(session, clan, lang),
        "rank": await clan_service.clan_rank(session, clan),
        "sectors_held": await clan_service.sectors_held(session, clan.id),
        "invite_link": clan_service.start_link(get_settings().bot_username, clan.id),
        "is_member": user.clan_id == clan.id,
        "is_owner": clan.owner_user_id == user.id,
        "top_members": [
            {"id": m.id, "first_name": m.first_name, "season_score": m.season_score}
            for m in members
        ],
    }


@router.post("/clans/{clan_id}/join", dependencies=[Depends(limit("clan_join", 10, 60))])
async def join_clan(
    clan_id: int,
    user: User = Depends(get_user_locked),
    session: AsyncSession = Depends(get_session),
) -> dict:
    now = player_service.utcnow()
    await clan_service.join_clan(session, user, clan_id, now)
    state = await build_state(session, user, now)
    await session.commit()
    return {"state": state}


@router.post("/clans/leave", dependencies=[Depends(limit("clan_join", 10, 60))])
async def leave_clan(
    user: User = Depends(get_user_locked),
    session: AsyncSession = Depends(get_session),
) -> dict:
    now = player_service.utcnow()
    await clan_service.join_militia(session, user, now)
    state = await build_state(session, user, now)
    await session.commit()
    return {"state": state}
