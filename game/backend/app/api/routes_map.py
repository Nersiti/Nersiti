import json

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_user, get_user_locked, limit
from app.db import get_session
from app.game import clan_service, economy, player_service, war_service, world_service
from app.game.errors import GameError
from app.game.state import build_state
from app.i18n import pick_lang
from app.models import BattleLog, City, Clan, Sector, User
from app.redis_client import get_redis

router = APIRouter()

MAX_CITIES = 500
MAX_SECTORS = 3000
MAX_SECTOR_BBOX_DEGREES = 6.0
CITIES_CACHE_SECONDS = 10


def parse_bbox(raw: str) -> tuple[float, float, float, float]:
    try:
        w, s, e, n = (float(x) for x in raw.split(","))
    except ValueError as exc:
        raise GameError("bad_bbox") from exc
    s, n = max(-90.0, min(s, n)), min(90.0, max(s, n))
    w, e = max(-180.0, w), min(180.0, e)
    return w, s, e, n


def bbox_filter(lat_col, lng_col, bbox: tuple[float, float, float, float]):
    w, s, e, n = bbox
    lng_cond = and_(lng_col >= w, lng_col <= e) if w <= e else or_(lng_col >= w, lng_col <= e)
    return and_(lat_col >= s, lat_col <= n, lng_cond)


async def clans_dict(session: AsyncSession, clan_ids: set[int], lang: str) -> dict[str, dict]:
    if not clan_ids:
        return {}
    clans = (await session.execute(select(Clan).where(Clan.id.in_(clan_ids)))).scalars().all()
    result = {}
    for c in clans:
        result[str(c.id)] = {
            "title": await clan_service.display_title(session, c, lang),
            "color": c.color,
            "is_militia": c.kind == clan_service.MILITIA,
        }
    return result


@router.get("/map/cities")
async def map_cities(
    bbox: str = Query(max_length=100),
    user: User = Depends(get_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    lang = pick_lang(user.language_code)
    box = parse_bbox(bbox)
    cache_key = f"mapcities:{lang}:" + ",".join(f"{x:.1f}" for x in box)
    redis = get_redis()
    if cached := await redis.get(cache_key):
        return json.loads(cached)

    cities = (
        (
            await session.execute(
                select(City)
                .where(City.sectors_count > 0, bbox_filter(City.lat, City.lng, box))
                .order_by(City.population.desc())
                .limit(MAX_CITIES)
            )
        )
        .scalars()
        .all()
    )
    body = {
        "cities": [
            {
                "id": c.id,
                "name": world_service.city_name(c, lang),
                "lat": c.lat,
                "lng": c.lng,
                "population": c.population,
                "controller_clan_id": c.controller_clan_id,
            }
            for c in cities
        ],
        "clans": await clans_dict(
            session, {c.controller_clan_id for c in cities if c.controller_clan_id}, lang
        ),
    }
    await redis.set(cache_key, json.dumps(body, ensure_ascii=False), ex=CITIES_CACHE_SECONDS)
    return body


@router.get("/map/sectors")
async def map_sectors(
    bbox: str = Query(max_length=100),
    user: User = Depends(get_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    lang = pick_lang(user.language_code)
    box = parse_bbox(bbox)
    w, s, e, n = box
    width = e - w if w <= e else 360 - (w - e)
    if width > MAX_SECTOR_BBOX_DEGREES or n - s > MAX_SECTOR_BBOX_DEGREES:
        raise GameError("bbox_too_large")

    rows = (
        (
            await session.execute(
                select(Sector)
                .where(bbox_filter(Sector.lat, Sector.lng, box))
                .order_by(Sector.value.desc())
                .limit(MAX_SECTORS + 1)
            )
        )
        .scalars()
        .all()
    )
    truncated = len(rows) > MAX_SECTORS
    rows = rows[:MAX_SECTORS]
    now = player_service.utcnow()
    sectors = []
    for sec in rows:
        shielded = sec.shield_until is not None and sec.shield_until > now
        sectors.append(
            [
                sec.h3,
                sec.owner_clan_id,
                economy.decayed_defense(sec.defense, sec.defense_updated_at, now),
                sec.value,
                1 if shielded else 0,
            ]
        )
    owners = {sec.owner_clan_id for sec in rows if sec.owner_clan_id}
    return {
        "sectors": sectors,
        "clans": await clans_dict(session, owners, lang),
        "truncated": truncated,
    }


@router.get("/sector/{h3}")
async def sector_details(
    h3: str,
    user: User = Depends(get_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    lang = pick_lang(user.language_code)
    sector = await session.get(Sector, h3)
    if sector is None:
        raise GameError("sector_not_found", 404)
    now = player_service.utcnow()
    city = await session.get(City, sector.city_id)
    owner = await session.get(Clan, sector.owner_clan_id) if sector.owner_clan_id else None
    my_clan = await session.get(Clan, user.clan_id) if user.clan_id else None

    foothold = False
    militia_blocked = False
    if my_clan is not None and sector.city_id != user.city_id:
        if my_clan.kind == clan_service.MILITIA:
            militia_blocked = True
        else:
            foothold = not await war_service.clan_has_sector_in_city(
                session, my_clan.id, sector.city_id
            )
    artillery = await war_service.artillery_active(session, user.id, now)

    log_rows = (
        await session.execute(
            select(BattleLog, User.first_name)
            .join(User, User.id == BattleLog.user_id)
            .where(BattleLog.sector_h3 == h3)
            .order_by(BattleLog.id.desc())
            .limit(5)
        )
    ).all()
    log_clans = await clans_dict(session, {row.BattleLog.clan_id for row in log_rows}, lang)

    return {
        **war_service.sector_dict(sector, now),
        "city": {"id": city.id, "name": world_service.city_name(city, lang)} if city else None,
        "owner": await clan_service.clan_summary(session, owner, lang) if owner else None,
        "is_own": owner is not None and my_clan is not None and owner.id == my_clan.id,
        "foothold": foothold,
        "militia_blocked": militia_blocked,
        "attack_mult": war_service.attack_mult(user, artillery),
        "defense_mult": economy.bp_to_mult(user.defense_bonus_bp),
        "foothold_divisor": economy.FOOTHOLD_DIVISOR,
        "min_amount": economy.MIN_ACTION_COINS,
        "log": [
            {
                "user": row.first_name,
                "clan": log_clans.get(str(row.BattleLog.clan_id)),
                "action": row.BattleLog.action,
                "power": row.BattleLog.power,
                "flipped": row.BattleLog.flipped,
                "at": row.BattleLog.created_at.isoformat(),
            }
            for row in log_rows
        ],
    }


class ActionIn(BaseModel):
    amount: int = Field(ge=1, le=10**15)


@router.post("/sector/{h3}/action", dependencies=[Depends(limit("sector_action", 40, 60))])
async def sector_action(
    h3: str,
    body: ActionIn,
    user: User = Depends(get_user_locked),
    session: AsyncSession = Depends(get_session),
) -> dict:
    now = player_service.utcnow()
    result = await war_service.act_on_sector(session, user, h3, body.amount, now)
    state = await build_state(session, user, now)
    await session.commit()
    return {"result": result, "state": state}
