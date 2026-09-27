import asyncio
from datetime import UTC, datetime, timedelta

import h3
import pytest
from sqlalchemy import func, select, update

from app.game import economy as e
from app.game import player_service
from app.models import BattleLog, City, Clan, Sector, User
from tests.helpers import auth, login, seed_world

T0 = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
KAZAN_CENTER = h3.latlng_to_cell(55.78874, 49.12214, 6)
MOSCOW_CENTER = h3.latlng_to_cell(55.75204, 37.61781, 6)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw) -> None:
        self.now += timedelta(**kw)


@pytest.fixture
def clock(monkeypatch) -> Clock:
    c = Clock()
    monkeypatch.setattr(player_service, "utcnow", c)
    return c


# --- Pure formulas -------------------------------------------------------------------


def test_decayed_defense():
    assert e.decayed_defense(1000, T0, T0 + timedelta(hours=1)) == 990
    assert e.decayed_defense(1000, T0, T0 + timedelta(hours=24)) == 785
    assert e.decayed_defense(1000, None, T0) == 1000
    assert e.decayed_defense(0, T0, T0 + timedelta(hours=5)) == 0


def test_resolve_battle_rules():
    assert e.resolve_battle(None, 0, 3, 7, 599) is None
    cap = e.resolve_battle(None, 0, 3, 7, 600)
    assert (cap.action, cap.owner_clan_id, cap.defense, cap.flipped) == ("capture", 7, 600, True)
    rein = e.resolve_battle(7, 600, 3, 7, 100)
    assert (rein.action, rein.defense, rein.flipped) == ("reinforce", 700, False)
    hit = e.resolve_battle(7, 600, 3, 9, 100)
    assert (hit.owner_clan_id, hit.defense, hit.flipped) == (7, 500, False)
    flip = e.resolve_battle(7, 600, 3, 9, 1000)
    assert (flip.owner_clan_id, flip.defense, flip.flipped) == (9, 400, True)
    exact = e.resolve_battle(7, 600, 3, 9, 600)
    assert (exact.owner_clan_id, exact.defense) == (7, 0)  # needs to go below zero
    assert e.resolve_battle(7, 4_999_990, 1, 7, 100).defense == 5_000_000  # capped


def test_action_power():
    assert e.action_power(1000, 1.15, False) == 1150
    assert e.action_power(1000, 1.0, True) == 333


# --- API -----------------------------------------------------------------------------


async def onboard(client, db, user_id: int, city_id: int, coins: int = 100_000) -> None:
    await login(client, user_id)
    res = await client.post(
        "/api/onboarding", json={"country_code": "RU", "city_id": city_id}, headers=auth(user_id)
    )
    assert res.status_code == 200, res.text
    await db.execute(update(User).where(User.id == user_id).values(coins=coins))
    await db.commit()


async def channel_clan(db, chat_id: int = -1) -> int:
    clan = Clan(kind="channel", tg_chat_id=chat_id, title=f"Channel {chat_id}", color="#ff0000")
    db.add(clan)
    await db.commit()
    return clan.id


async def put_in_clan(db, user_id: int, clan_id: int) -> None:
    await db.execute(update(User).where(User.id == user_id).values(clan_id=clan_id))
    await db.commit()


async def act(client, user_id: int, h3_cell: str, amount: int):
    return await client.post(
        f"/api/sector/{h3_cell}/action", json={"amount": amount}, headers=auth(user_id)
    )


async def test_capture_attack_and_reinforce(client, db, clock):
    ids = await seed_world(db)
    await onboard(client, db, 1, ids["kazan"], coins=1000)
    await onboard(client, db, 2, ids["kazan"])
    enemy = await channel_clan(db)
    await put_in_clan(db, 2, enemy)

    res = await act(client, 1, KAZAN_CENTER, 500)
    assert res.status_code == 400
    assert res.json()["detail"] == "not_enough_power"
    assert (await db.get(User, 1)).coins == 1000

    res = await act(client, 1, KAZAN_CENTER, 600)
    body = res.json()
    assert body["result"]["action"] == "capture"
    assert body["result"]["sector"]["defense"] == 600
    assert body["state"]["coins"] == 400
    user1 = await db.get(User, 1)
    await db.refresh(user1)
    assert user1.season_score == 600 + 300
    militia_id = user1.clan_id
    city = await db.get(City, ids["kazan"])
    await db.refresh(city)
    assert city.controller_clan_id == militia_id

    res = await act(client, 2, KAZAN_CENTER, 700)
    result = res.json()["result"]
    assert (result["flipped"], result["sector"]["owner_clan_id"]) == (True, enemy)
    assert result["sector"]["defense"] == 100
    await db.refresh(city)
    assert city.controller_clan_id == enemy

    clock.advance(seconds=3)
    res = await act(client, 2, KAZAN_CENTER, 50)
    assert res.json()["result"]["action"] == "reinforce"
    # 100 decayed for 3 seconds -> 99, then +50
    assert res.json()["result"]["sector"]["defense"] == 149

    logs = (await db.execute(select(func.count()).select_from(BattleLog))).scalar_one()
    assert logs == 3


async def test_militia_fights_only_at_home(client, db, clock):
    ids = await seed_world(db)
    await onboard(client, db, 1, ids["kazan"])
    res = await act(client, 1, MOSCOW_CENTER, 5000)
    assert res.status_code == 403
    assert res.json()["detail"] == "militia_home_only"


async def test_foothold_divides_power_until_clan_holds_a_sector(client, db, clock):
    ids = await seed_world(db)
    await onboard(client, db, 1, ids["kazan"])
    await put_in_clan(db, 1, await channel_clan(db))
    moscow_edge = next(
        s.h3
        for s in (
            await db.execute(
                select(Sector).where(Sector.city_id == ids["moscow"], Sector.value == 1)
            )
        ).scalars()
    )
    res = await act(client, 1, moscow_edge, 599)  # 599 // 3 = 199 < 200
    assert res.json()["detail"] == "not_enough_power"
    clock.advance(seconds=3)
    res = await act(client, 1, moscow_edge, 600)
    assert res.json()["result"]["foothold"] is True
    assert res.json()["result"]["sector"]["defense"] == 200

    clock.advance(seconds=3)
    other = next(
        s.h3
        for s in (
            await db.execute(
                select(Sector).where(
                    Sector.city_id == ids["moscow"],
                    Sector.value == 1,
                    Sector.h3 != moscow_edge,
                )
            )
        ).scalars()
    )
    res = await act(client, 1, other, 200)
    assert res.json()["result"]["foothold"] is False


async def test_shield_blocks_enemies_but_not_owner(client, db, clock):
    ids = await seed_world(db)
    await onboard(client, db, 1, ids["kazan"])
    await onboard(client, db, 2, ids["kazan"])
    await put_in_clan(db, 2, await channel_clan(db))
    await act(client, 1, KAZAN_CENTER, 1000)
    await db.execute(
        update(Sector).where(Sector.h3 == KAZAN_CENTER).values(shield_until=T0 + timedelta(hours=8))
    )
    await db.commit()
    res = await act(client, 2, KAZAN_CENTER, 5000)
    assert res.status_code == 403
    assert res.json()["detail"] == "sector_shielded"
    clock.advance(seconds=3)
    assert (await act(client, 1, KAZAN_CENTER, 100)).status_code == 200


async def test_action_cooldown_and_validation(client, db, clock):
    ids = await seed_world(db)
    await onboard(client, db, 1, ids["kazan"], coins=5000)
    assert (await act(client, 1, KAZAN_CENTER, 1000)).status_code == 200
    res = await act(client, 1, KAZAN_CENTER, 100)
    assert res.status_code == 429
    assert res.json()["detail"] == "action_cooldown"
    clock.advance(seconds=2)
    assert (await act(client, 1, KAZAN_CENTER, 100)).status_code == 200
    clock.advance(seconds=2)
    assert (await act(client, 1, KAZAN_CENTER, 5)).json()["detail"] == "amount_too_small"
    assert (await act(client, 1, KAZAN_CENTER, 10**9)).json()["detail"] == "not_enough_coins"
    assert (await act(client, 1, "86ffffffffffff", 100)).status_code == 404


async def test_defense_decays_over_time(client, db, clock):
    ids = await seed_world(db)
    await onboard(client, db, 1, ids["kazan"])
    await act(client, 1, KAZAN_CENTER, 1000)
    clock.advance(hours=24)
    details = (await client.get(f"/api/sector/{KAZAN_CENTER}", headers=auth(1))).json()
    assert details["defense"] == 785
    assert details["is_own"] is True
    assert details["log"][0]["action"] == "capture"
    assert details["city"]["name"] == "Казань"


async def test_map_endpoints(client, db, clock):
    ids = await seed_world(db)
    await onboard(client, db, 1, ids["kazan"])
    await act(client, 1, KAZAN_CENTER, 1000)
    militia = (await db.get(User, 1)).clan_id

    res = await client.get(
        "/api/map/sectors", params={"bbox": "48.5,55.4,49.8,56.2"}, headers=auth(1)
    )
    body = res.json()
    assert len(body["sectors"]) == 61
    owned = [s for s in body["sectors"] if s[0] == KAZAN_CENTER][0]
    assert owned[1:4] == [militia, 1000, 3]
    assert body["clans"][str(militia)]["title"] == "Ополчение: Казань"

    res = await client.get("/api/map/sectors", params={"bbox": "30,50,60,60"}, headers=auth(1))
    assert res.json()["detail"] == "bbox_too_large"

    res = await client.get("/api/map/cities", params={"bbox": "30,40,60,60"}, headers=auth(1))
    cities = {c["name"]: c for c in res.json()["cities"]}
    assert cities["Казань"]["controller_clan_id"] == militia
    assert "Москва" in cities


async def test_concurrent_attacks_are_serialized(client, db, clock):
    ids = await seed_world(db)
    await onboard(client, db, 1, ids["kazan"])
    await act(client, 1, KAZAN_CENTER, 10_000)
    enemy = await channel_clan(db)
    attackers = list(range(100, 120))
    for uid in attackers:
        await onboard(client, db, uid, ids["kazan"], coins=1000)
        await put_in_clan(db, uid, enemy)

    results = await asyncio.gather(*(act(client, uid, KAZAN_CENTER, 100) for uid in attackers))
    assert all(r.status_code == 200 for r in results), [r.text for r in results]

    sector = await db.get(Sector, KAZAN_CENTER)
    await db.refresh(sector)
    assert sector.defense == 10_000 - 20 * 100
    spent = (
        await db.execute(select(func.sum(User.coins)).where(User.id.in_(attackers)))
    ).scalar_one()
    assert spent == 20 * 900
    logs = (await db.execute(select(func.count()).select_from(BattleLog))).scalar_one()
    assert logs == 21
