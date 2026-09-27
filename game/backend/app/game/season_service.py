"""Seasons: hourly control points, results, rewards and the map reset (PLAN.md, B)."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.game import economy
from app.models import City, Clan, Season, Sector, User, UserBadge
from app.redis_client import get_redis

log = logging.getLogger(__name__)


async def get_active_season(session: AsyncSession) -> Season | None:
    return (
        await session.execute(
            select(Season).where(Season.status == "active").order_by(Season.number.desc()).limit(1)
        )
    ).scalar_one_or_none()


async def ensure_active_season(session: AsyncSession, now: datetime) -> Season:
    season = await get_active_season(session)
    if season is not None:
        return season
    last_number = (await session.execute(select(func.max(Season.number)))).scalar_one() or 0
    await session.execute(
        insert(Season)
        .values(
            number=last_number + 1,
            starts_at=now,
            ends_at=now + timedelta(days=economy.SEASON_DAYS),
            status="active",
        )
        .on_conflict_do_nothing(index_elements=[Season.number])
    )
    return await get_active_season(session)


async def accrue_control_points(session: AsyncSession, now: datetime) -> bool:
    """Adds Σ value of held sectors to every clan. At most once per clock hour."""
    hour_key = f"accrual:{now:%Y%m%d%H}"
    if not await get_redis().set(hour_key, "1", ex=3 * 3600, nx=True):
        return False
    await session.execute(
        text(
            """
            UPDATE clans SET season_points = clans.season_points + held.points
            FROM (
                SELECT owner_clan_id, SUM(value) AS points
                FROM sectors WHERE owner_clan_id IS NOT NULL
                GROUP BY owner_clan_id
            ) AS held
            WHERE clans.id = held.owner_clan_id
            """
        )
    )
    return True


async def recompute_all_controllers(session: AsyncSession) -> None:
    """Fixes any drift in cities.controller_clan_id (normally updated on every flip)."""
    await session.execute(
        text(
            """
            WITH totals AS (
                SELECT city_id, owner_clan_id, SUM(value) AS points
                FROM sectors WHERE owner_clan_id IS NOT NULL
                GROUP BY city_id, owner_clan_id
            ), ranked AS (
                SELECT city_id, owner_clan_id,
                       ROW_NUMBER() OVER (PARTITION BY city_id ORDER BY points DESC, owner_clan_id)
                           AS rn,
                       MAX(points) OVER (PARTITION BY city_id) AS top
                FROM totals
            )
            UPDATE cities SET controller_clan_id = ranked.owner_clan_id
            FROM ranked
            WHERE ranked.city_id = cities.id AND ranked.rn = 1
              AND cities.controller_clan_id IS DISTINCT FROM ranked.owner_clan_id
              AND NOT EXISTS (
                  SELECT 1 FROM totals t
                  WHERE t.city_id = cities.id AND t.owner_clan_id = cities.controller_clan_id
                    AND t.points = ranked.top
              )
            """
        )
    )
    await session.execute(
        text(
            """
            UPDATE cities SET controller_clan_id = NULL
            WHERE controller_clan_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM sectors s
                              WHERE s.city_id = cities.id AND s.owner_clan_id IS NOT NULL)
            """
        )
    )


async def compute_results(session: AsyncSession) -> dict:
    top_clans = (
        (
            await session.execute(
                select(Clan)
                .where(Clan.banned.is_(False), Clan.season_points > 0)
                .order_by(Clan.season_points.desc(), Clan.id)
                .limit(economy.SEASON_TOP_CLANS)
            )
        )
        .scalars()
        .all()
    )
    top_players = (
        (
            await session.execute(
                select(User)
                .where(User.banned.is_(False), User.season_score > 0)
                .order_by(User.season_score.desc(), User.id)
                .limit(economy.SEASON_TOP_PLAYERS)
            )
        )
        .scalars()
        .all()
    )
    countries = (
        await session.execute(
            select(User.country_code, func.sum(User.season_score).label("score"))
            .where(User.country_code.is_not(None), User.banned.is_(False))
            .group_by(User.country_code)
            .having(func.sum(User.season_score) > 0)
            .order_by(text("score DESC"))
            .limit(20)
        )
    ).all()
    best_cities = (
        await session.execute(
            text(
                """
                SELECT DISTINCT ON (c.country_code) c.country_code, c.id, c.name_en, c.name_ru,
                       t.score
                FROM (
                    SELECT city_id, SUM(season_score) AS score FROM users
                    WHERE city_id IS NOT NULL AND NOT banned GROUP BY city_id
                ) t JOIN cities c ON c.id = t.city_id
                WHERE t.score > 0
                ORDER BY c.country_code, t.score DESC, c.id
                """
            )
        )
    ).all()
    return {
        "clans": [
            {
                "id": c.id,
                "title": c.title,
                "kind": c.kind,
                "city_id": c.city_id,
                "color": c.color,
                "points": c.season_points,
            }
            for c in top_clans
        ],
        "players": [
            {"id": u.id, "first_name": u.first_name, "score": u.season_score} for u in top_players
        ],
        "countries": [{"code": code, "score": int(score)} for code, score in countries],
        "best_cities": [
            {
                "country_code": r.country_code,
                "city_id": r.id,
                "name_en": r.name_en,
                "name_ru": r.name_ru,
                "score": int(r.score),
            }
            for r in best_cities
        ],
    }


async def _award(session: AsyncSession, season: Season, results: dict) -> None:
    for place, clan in enumerate(results["clans"], start=1):
        reward = economy.SEASON_CLAN_MEMBER_REWARDS[place - 1]
        member_ids = (
            (await session.execute(select(User.id).where(User.clan_id == clan["id"])))
            .scalars()
            .all()
        )
        await session.execute(
            update(User)
            .where(User.clan_id == clan["id"])
            .values(coins=User.coins + reward, total_earned=User.total_earned + reward)
        )
        await _badges(session, member_ids, f"clan_top{place}", season.id)

    for place, player in enumerate(results["players"], start=1):
        reward = economy.season_player_reward(place)
        await session.execute(
            update(User)
            .where(User.id == player["id"])
            .values(coins=User.coins + reward, total_earned=User.total_earned + reward)
        )
        badge = f"player_top{place}" if place <= 3 else "player_top100"
        await _badges(session, [player["id"]], badge, season.id)


async def _badges(session: AsyncSession, user_ids: list[int], badge_id: str, season_id: int):
    if not user_ids:
        return
    await session.execute(
        insert(UserBadge)
        .values(
            [{"user_id": uid, "badge_id": badge_id, "season_id": season_id} for uid in user_ids]
        )
        .on_conflict_do_nothing()
    )


async def _reset_map(session: AsyncSession) -> None:
    await session.execute(
        update(Sector)
        .where((Sector.owner_clan_id.is_not(None)) | (Sector.defense > 0))
        .values(
            owner_clan_id=None,
            defense=0,
            defense_updated_at=None,
            shield_until=None,
            captured_at=None,
        )
    )
    await session.execute(update(Clan).where(Clan.season_points != 0).values(season_points=0))
    await session.execute(update(User).where(User.season_score != 0).values(season_score=0))
    await session.execute(
        update(City).where(City.controller_clan_id.is_not(None)).values(controller_clan_id=None)
    )


async def end_season(
    session: AsyncSession, now: datetime, *, apply: bool, force: bool = False
) -> dict | None:
    """Finishes the active season if it is over (or `force`). Idempotent: a second run
    finds no active season to finish. Returns the results, or None if nothing to do."""
    season = (
        await session.execute(
            select(Season).where(Season.status == "active").with_for_update().limit(1)
        )
    ).scalar_one_or_none()
    if season is None or (season.ends_at > now and not force):
        return None
    results = await compute_results(session)
    results["season"] = season.number
    if not apply:
        return results

    await _award(session, season, results)
    await _reset_map(session)
    season.status = "finished"
    season.results = results
    session.add(
        Season(
            number=season.number + 1,
            starts_at=now,
            ends_at=now + timedelta(days=economy.SEASON_DAYS),
            status="active",
        )
    )
    log.info("Season %s finished; season %s started", season.number, season.number + 1)
    return results
