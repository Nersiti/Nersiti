from datetime import UTC, datetime, timedelta

import h3
from sqlalchemy import func, select, update

from app.game import player_service, season_service
from app.models import City, Clan, Season, Sector, User, UserBadge
from tests.helpers import auth, login, seed_world

T0 = datetime(2026, 6, 1, 10, 30, tzinfo=UTC)
KAZAN_CENTER = h3.latlng_to_cell(55.78874, 49.12214, 6)


async def onboard(client, db, user_id, city_id, country="RU", score=0) -> User:
    await login(client, user_id)
    await client.post(
        "/api/onboarding", json={"country_code": country, "city_id": city_id}, headers=auth(user_id)
    )
    await db.execute(update(User).where(User.id == user_id).values(season_score=score))
    await db.commit()
    return await db.get(User, user_id)


async def own_sectors(db, clan_id: int, city_id: int, count: int) -> None:
    rows = (
        (await db.execute(select(Sector).where(Sector.city_id == city_id).limit(count)))
        .scalars()
        .all()
    )
    for s in rows:
        s.owner_clan_id = clan_id
        s.defense = 1000
    await db.commit()


async def test_control_points_accrue_once_per_hour(client, db):
    ids = await seed_world(db)
    user = await onboard(client, db, 1, ids["kazan"])
    await own_sectors(db, user.clan_id, ids["kazan"], 5)
    expected = sum(
        s.value
        for s in (await db.execute(select(Sector).where(Sector.owner_clan_id == user.clan_id)))
        .scalars()
        .all()
    )
    assert await season_service.accrue_control_points(db, T0) is True
    assert await season_service.accrue_control_points(db, T0 + timedelta(minutes=20)) is False
    await db.commit()
    clan = await db.get(Clan, user.clan_id)
    await db.refresh(clan)
    assert clan.season_points == expected
    assert await season_service.accrue_control_points(db, T0 + timedelta(hours=1)) is True


async def test_recompute_controllers_fixes_drift(client, db):
    ids = await seed_world(db)
    user = await onboard(client, db, 1, ids["kazan"])
    await own_sectors(db, user.clan_id, ids["kazan"], 3)
    await db.execute(update(City).where(City.id == ids["moscow"]).values(controller_clan_id=999))
    await db.commit()
    await season_service.recompute_all_controllers(db)
    await db.commit()
    kazan, moscow = await db.get(City, ids["kazan"]), await db.get(City, ids["moscow"])
    await db.refresh(kazan)
    await db.refresh(moscow)
    assert kazan.controller_clan_id == user.clan_id
    assert moscow.controller_clan_id is None


async def test_end_season_dry_run_changes_nothing(client, db):
    ids = await seed_world(db)
    user = await onboard(client, db, 1, ids["kazan"], score=500)
    await own_sectors(db, user.clan_id, ids["kazan"], 3)
    await db.execute(update(Clan).where(Clan.id == user.clan_id).values(season_points=77))
    await season_service.ensure_active_season(db, T0)
    await db.commit()

    results = await season_service.end_season(db, T0, apply=False, force=True)
    await db.rollback()
    assert results["clans"][0]["points"] == 77
    assert results["players"][0]["score"] == 500
    assert results["countries"] == [{"code": "RU", "score": 500}]
    assert results["best_cities"][0]["city_id"] == ids["kazan"]
    owned = (
        await db.execute(
            select(func.count()).select_from(Sector).where(Sector.owner_clan_id.is_not(None))
        )
    ).scalar_one()
    assert owned == 3


async def test_end_season_awards_resets_and_is_idempotent(client, db):
    ids = await seed_world(db)
    winner = await onboard(client, db, 1, ids["kazan"], score=900)
    teammate = await onboard(client, db, 2, ids["kazan"], score=100)
    other = await onboard(client, db, 3, ids["moscow"], score=50)
    await own_sectors(db, winner.clan_id, ids["kazan"], 3)
    await db.execute(update(Clan).where(Clan.id == winner.clan_id).values(season_points=1000))
    await db.execute(update(Clan).where(Clan.id == other.clan_id).values(season_points=10))
    season = await season_service.ensure_active_season(db, T0)
    await db.commit()
    ends_at = season.ends_at

    # Not over yet and not forced: nothing happens.
    assert await season_service.end_season(db, T0, apply=True) is None
    await db.rollback()

    end = ends_at + timedelta(minutes=1)
    results = await season_service.end_season(db, end, apply=True)
    await db.commit()
    assert results["season"] == 1

    for u in (winner, teammate, other):
        await db.refresh(u)
    # Winner: clan place 1 (500k) + player place 1 (1M); teammate: 500k + player place 2 (500k)
    assert winner.coins == 1000 + 500_000 + 1_000_000
    assert teammate.coins == 1000 + 500_000 + 500_000
    assert other.coins == 1000 + 250_000 + 250_000  # clan place 2, player place 3
    assert winner.season_score == teammate.season_score == 0

    badges = (
        (await db.execute(select(UserBadge.badge_id).where(UserBadge.user_id == 1))).scalars().all()
    )
    assert set(badges) == {"clan_top1", "player_top1"}

    owned = (
        await db.execute(
            select(func.count()).select_from(Sector).where(Sector.owner_clan_id.is_not(None))
        )
    ).scalar_one()
    assert owned == 0
    points = (await db.execute(select(func.sum(Clan.season_points)))).scalar_one()
    assert points == 0

    seasons = (await db.execute(select(Season).order_by(Season.number))).scalars().all()
    assert [(s.number, s.status) for s in seasons] == [(1, "finished"), (2, "active")]
    assert seasons[0].results["clans"][0]["id"] == winner.clan_id

    # Running again right after does nothing: season 2 is not over.
    assert await season_service.end_season(db, end, apply=True) is None


async def test_leaderboards_and_season_endpoint(client, db, monkeypatch):
    monkeypatch.setattr(player_service, "utcnow", lambda: T0)
    ids = await seed_world(db)
    await onboard(client, db, 1, ids["kazan"], score=300)
    await onboard(client, db, 2, ids["kazan"], score=500)
    await onboard(client, db, 3, ids["moscow"], score=100)
    await onboard(client, db, 4, ids["kazan_tr"], country="TR", score=1000)

    body = (await client.get("/api/leaderboard/players", headers=auth(1))).json()
    assert [p["id"] for p in body["items"]] == [4, 2, 1, 3]
    assert body["me"] == {"rank": 3, "score": 300}

    body = (await client.get("/api/leaderboard/players?scope=city", headers=auth(1))).json()
    assert [p["id"] for p in body["items"]] == [2, 1]
    assert body["me"]["rank"] == 2

    body = (await client.get("/api/leaderboard/countries", headers=auth(1))).json()
    assert [(c["code"], c["score"]) for c in body["items"]] == [("TR", 1000), ("RU", 900)]
    assert body["items"][1]["name"] == "Россия"
    assert body["me"]["rank"] == 2

    body = (await client.get("/api/leaderboard/cities", headers=auth(1))).json()
    assert [c["name"] for c in body["items"]] == ["Казан", "Казань", "Москва"]
    assert body["me"]["rank"] == 2

    body = (await client.get("/api/leaderboard/clans", headers=auth(1))).json()
    assert len(body["items"]) == 3
    assert body["me"]["rank"] >= 1

    season = (await client.get("/api/season", headers=auth(1))).json()
    assert season["number"] == 1
    assert season["seconds_left"] == 30 * 24 * 3600
    assert season["hall_of_fame"] == []
