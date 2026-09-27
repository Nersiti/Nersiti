import json
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_user
from app.db import get_session
from app.game import clan_service, player_service, season_service, world_service
from app.i18n import pick_lang
from app.models import City, Clan, Season, User
from app.redis_client import get_redis

router = APIRouter()

TOP_LIMIT = 100
CACHE_SECONDS = 60


async def _cached(key: str, build) -> list:
    redis = get_redis()
    if (raw := await redis.get(key)) is not None:
        return json.loads(raw)
    items = await build()
    await redis.set(key, json.dumps(items, ensure_ascii=False), ex=CACHE_SECONDS)
    return items


@router.get("/leaderboard/players")
async def players(
    scope: Literal["global", "country", "city"] = "global",
    user: User = Depends(get_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    filters = [User.banned.is_(False)]
    scope_key = "all"
    if scope == "country" and user.country_code:
        filters.append(User.country_code == user.country_code)
        scope_key = user.country_code
    elif scope == "city" and user.city_id:
        filters.append(User.city_id == user.city_id)
        scope_key = str(user.city_id)

    async def build() -> list:
        rows = (
            await session.execute(
                select(User.id, User.first_name, User.season_score, User.country_code)
                .where(*filters)
                .order_by(User.season_score.desc(), User.id)
                .limit(TOP_LIMIT)
            )
        ).all()
        return [
            {
                "id": r.id,
                "name": r.first_name,
                "score": r.season_score,
                "country_code": r.country_code,
            }
            for r in rows
        ]

    items = await _cached(f"lb:players:{scope}:{scope_key}", build)
    better = (
        await session.execute(
            select(func.count())
            .select_from(User)
            .where(*filters, User.season_score > user.season_score)
        )
    ).scalar_one()
    return {"items": items, "me": {"rank": better + 1, "score": user.season_score}}


@router.get("/leaderboard/clans")
async def clans(
    user: User = Depends(get_user), session: AsyncSession = Depends(get_session)
) -> dict:
    lang = pick_lang(user.language_code)

    async def build() -> list:
        rows = (
            (
                await session.execute(
                    select(Clan)
                    .where(Clan.banned.is_(False), Clan.members_count > 0)
                    .order_by(Clan.season_points.desc(), Clan.id)
                    .limit(TOP_LIMIT)
                )
            )
            .scalars()
            .all()
        )
        return [await clan_service.clan_summary(session, c, lang) for c in rows]

    items = await _cached(f"lb:clans:{lang}", build)
    me = None
    if user.clan_id and (clan := await session.get(Clan, user.clan_id)):
        me = {"rank": await clan_service.clan_rank(session, clan), "score": clan.season_points}
    return {"items": items, "me": me}


@router.get("/leaderboard/countries")
async def countries(
    user: User = Depends(get_user), session: AsyncSession = Depends(get_session)
) -> dict:
    lang = pick_lang(user.language_code)

    async def build() -> list:
        rows = (
            await session.execute(
                select(User.country_code, func.sum(User.season_score).label("score"))
                .where(User.country_code.is_not(None), User.banned.is_(False))
                .group_by(User.country_code)
                .order_by(text("score DESC"), User.country_code)
                .limit(TOP_LIMIT)
            )
        ).all()
        return [
            {"code": code, "name": world_service.country_name(code, lang), "score": int(score)}
            for code, score in rows
        ]

    items = await _cached(f"lb:countries:{lang}", build)
    rank = next((i + 1 for i, c in enumerate(items) if c["code"] == user.country_code), None)
    return {"items": items, "me": {"rank": rank, "code": user.country_code}}


@router.get("/leaderboard/cities")
async def cities(
    country: str | None = Query(default=None, min_length=2, max_length=2),
    user: User = Depends(get_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    lang = pick_lang(user.language_code)
    country = country.upper() if country else None

    async def build() -> list:
        totals = (
            select(User.city_id, func.sum(User.season_score).label("score"))
            .where(User.city_id.is_not(None), User.banned.is_(False))
            .group_by(User.city_id)
            .subquery()
        )
        stmt = (
            select(City, totals.c.score)
            .join(totals, totals.c.city_id == City.id)
            .order_by(totals.c.score.desc(), City.id)
            .limit(TOP_LIMIT)
        )
        if country:
            stmt = stmt.where(City.country_code == country)
        rows = (await session.execute(stmt)).all()
        return [
            {
                "id": c.id,
                "name": world_service.city_name(c, lang),
                "country_code": c.country_code,
                "score": int(score),
            }
            for c, score in rows
        ]

    items = await _cached(f"lb:cities:{lang}:{country or 'all'}", build)
    rank = next((i + 1 for i, c in enumerate(items) if c["id"] == user.city_id), None)
    return {"items": items, "me": {"rank": rank, "city_id": user.city_id}}


@router.get("/season")
async def season(
    user: User = Depends(get_user), session: AsyncSession = Depends(get_session)
) -> dict:
    now = player_service.utcnow()
    current = await season_service.ensure_active_season(session, now)
    await session.commit()
    finished = (
        (
            await session.execute(
                select(Season)
                .where(Season.status == "finished")
                .order_by(Season.number.desc())
                .limit(5)
            )
        )
        .scalars()
        .all()
    )
    return {
        "number": current.number,
        "starts_at": current.starts_at.isoformat(),
        "ends_at": current.ends_at.isoformat(),
        "seconds_left": max(0, int((current.ends_at - now).total_seconds())),
        "hall_of_fame": [
            {"number": s.number, "clans": (s.results or {}).get("clans", [])[:3]} for s in finished
        ],
    }
