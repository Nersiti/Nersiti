from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics import track
from app.api.deps import get_user, get_user_locked, limit
from app.db import get_session
from app.game import clan_service, player_service, world_service
from app.game.state import build_state
from app.i18n import pick_lang
from app.models import City, Clan, User

router = APIRouter()


@router.get("/countries")
async def countries(
    user: User = Depends(get_user), session: AsyncSession = Depends(get_session)
) -> dict:
    lang = pick_lang(user.language_code)
    return {
        "items": await world_service.list_countries(session, lang),
        "suggested": world_service.suggest_country(user.language_code),
    }


@router.get("/cities/search", dependencies=[Depends(limit("city_search", 60, 60))])
async def cities_search(
    q: str = Query(min_length=1, max_length=64),
    country: str | None = Query(default=None, min_length=2, max_length=2),
    user: User = Depends(get_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    lang = pick_lang(user.language_code)
    items = await world_service.search_cities(
        session, q, lang, country.upper() if country else None
    )
    return {"items": items}


class OnboardingIn(BaseModel):
    country_code: str = Field(min_length=2, max_length=2)
    city_id: int


@router.post("/onboarding")
async def onboarding(
    body: OnboardingIn,
    user: User = Depends(get_user_locked),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if user.city_id is not None:
        raise HTTPException(status_code=409, detail="already_onboarded")
    country = body.country_code.upper()
    if country not in await world_service.country_codes(session):
        raise HTTPException(status_code=400, detail="unknown_country")
    city = await session.get(City, body.city_id)
    if city is None or city.sectors_count == 0:
        raise HTTPException(status_code=400, detail="unknown_city")

    user.country_code = country
    user.city_id = city.id
    now = player_service.utcnow()
    await clan_service.join_militia(session, user, now)
    await _join_referrer_clan(session, user, now)
    track(session, "onboarding", user.id, city=city.id, country=country)
    state = await build_state(session, user)
    await session.commit()
    return {"state": state}


async def _join_referrer_clan(session: AsyncSession, user: User, now) -> None:
    """Invited players start in their inviter's clan (unless it is a militia or
    subscribers-only: then the invite sheet handles it)."""
    if user.referrer_id is None:
        return
    inviter = await session.get(User, user.referrer_id)
    if inviter is None or inviter.clan_id is None:
        return
    clan = await session.get(Clan, inviter.clan_id)
    if clan is None or clan.banned or clan.kind == clan_service.MILITIA or clan.subscribers_only:
        return
    await clan_service.join_clan(session, user, clan.id, now)
