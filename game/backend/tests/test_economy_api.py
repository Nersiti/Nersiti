from datetime import UTC, datetime, timedelta

import pytest

from app.game import player_service
from app.models import DailyCombo, User, UserUpgrade
from tests.helpers import auth, login

T0 = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def advance(self, **kwargs) -> None:
        self.now += timedelta(**kwargs)

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock(monkeypatch) -> Clock:
    c = Clock(T0)
    monkeypatch.setattr(player_service, "utcnow", c)
    return c


async def set_user(db, user_id: int, **fields) -> None:
    user = await db.get(User, user_id)
    for k, v in fields.items():
        setattr(user, k, v)
    await db.commit()


async def test_taps_add_coins_and_spend_energy(client, clock):
    await login(client, 1)
    clock.advance(seconds=10)
    res = await client.post("/api/tap", json={"taps": 100}, headers=auth(1))
    body = res.json()
    assert body["earned"] == 100
    assert body["state"]["coins"] == 1100
    assert body["state"]["energy"] == 900


async def test_autoclicker_is_capped_and_flagged(client, db, clock):
    await login(client, 1)
    clock.advance(seconds=10)
    await client.post("/api/tap", json={"taps": 10}, headers=auth(1))
    clock.advance(seconds=1)
    res = await client.post("/api/tap", json={"taps": 100}, headers=auth(1))
    assert res.json()["earned"] == 15
    user = await db.get(User, 1)
    assert user.suspicion == 1


async def test_taps_cannot_exceed_energy(client, db, clock):
    await login(client, 1)
    await set_user(db, 1, energy=30, energy_updated_at=clock.now)
    clock.advance(seconds=10)  # +20 energy regenerated
    res = await client.post("/api/tap", json={"taps": 100}, headers=auth(1))
    assert res.json()["earned"] == 50
    assert res.json()["state"]["energy"] == 0


async def test_passive_income_for_an_hour_and_offline_cap(client, clock):
    await login(client, 1)
    res = await client.post("/api/upgrades/market/buy", headers=auth(1))
    assert res.status_code == 200, res.text
    assert res.json()["state"]["income_per_hour"] == 12
    assert res.json()["state"]["coins"] == 900

    clock.advance(hours=1)
    session = await login(client, 1)
    assert session["offline_earned"] == 12
    assert session["state"]["coins"] == 912

    clock.advance(hours=10)
    session = await login(client, 1)
    assert session["offline_earned"] == 36  # 3h cap


async def test_vip_extends_cap_and_multiplies_income(client, db, clock):
    await login(client, 1)
    await client.post("/api/upgrades/market/buy", headers=auth(1))
    await set_user(db, 1, vip_until=T0 + timedelta(days=30))
    clock.advance(hours=10)
    session = await login(client, 1)
    assert session["offline_earned"] == 180  # 12 * 1.5 * 10h
    assert session["state"]["offline_cap_hours"] == 12


async def test_upgrade_errors(client, db, clock):
    await login(client, 1)
    await set_user(db, 1, coins=50)
    res = await client.post("/api/upgrades/market/buy", headers=auth(1))
    assert res.status_code == 400
    assert res.json()["detail"] == "not_enough_coins"

    db.add(UserUpgrade(user_id=1, card_id="multitap", level=10))
    await set_user(db, 1, coins=10**9)
    res = await client.post("/api/upgrades/multitap/buy", headers=auth(1))
    assert res.json()["detail"] == "max_level"

    res = await client.post("/api/upgrades/nope/buy", headers=auth(1))
    assert res.status_code == 404


async def test_boost_cards_change_tap_power_and_energy(client, db, clock):
    await login(client, 1)
    await set_user(db, 1, coins=10_000)
    state = (await client.post("/api/upgrades/multitap/buy", headers=auth(1))).json()["state"]
    assert state["tap_power"] == 2
    state = (await client.post("/api/upgrades/battery/buy", headers=auth(1))).json()["state"]
    assert state["energy_max"] == 1500
    state = (await client.post("/api/upgrades/barracks/buy", headers=auth(1))).json()["state"]
    assert state["attack_mult"] == pytest.approx(1.03)


async def test_level_up_raises_tap_power(client, db, clock):
    await login(client, 1)
    await set_user(db, 1, total_earned=4_990)
    clock.advance(seconds=10)
    res = await client.post("/api/tap", json={"taps": 10}, headers=auth(1))
    state = res.json()["state"]
    assert state["total_earned"] == 5_000
    assert state["level"] == 2
    assert state["tap_power"] == 2
    assert (state["level_from"], state["level_to"]) == (5_000, 25_000)


async def test_daily_reward_streak(client, clock):
    await login(client, 1)
    res = await client.post("/api/daily/claim", headers=auth(1))
    assert res.json()["reward"] == 500
    assert res.json()["state"]["daily"]["claimed_today"] is True
    again = await client.post("/api/daily/claim", headers=auth(1))
    assert again.status_code == 409
    clock.advance(days=1)
    res = await client.post("/api/daily/claim", headers=auth(1))
    assert res.json()["reward"] == 1000
    assert res.json()["state"]["daily"]["next_reward"] == 2500


async def test_daily_combo_pays_once_when_all_three_found(client, db, clock):
    await login(client, 1)
    db.add(DailyCombo(day=T0.date(), card_ids=["market", "walls", "barracks"]))
    await set_user(db, 1, coins=100_000)

    status = (await client.get("/api/upgrades", headers=auth(1))).json()["combo"]
    assert status == {"found": [], "total": 3, "reward": 20_000, "claimed": False}

    r1 = (await client.post("/api/upgrades/market/buy", headers=auth(1))).json()
    r2 = (await client.post("/api/upgrades/workshop/buy", headers=auth(1))).json()
    r3 = (await client.post("/api/upgrades/walls/buy", headers=auth(1))).json()
    assert r1["combo_reward"] == r2["combo_reward"] == r3["combo_reward"] == 0
    assert r3["combo"]["found"] == ["market", "walls"]
    r4 = (await client.post("/api/upgrades/barracks/buy", headers=auth(1))).json()
    assert r4["combo_reward"] == 20_000
    assert r4["combo"]["claimed"] is True
    r5 = (await client.post("/api/upgrades/market/buy", headers=auth(1))).json()
    assert r5["combo_reward"] == 0


async def test_upgrades_list(client, clock):
    await login(client, 1)
    await client.post("/api/upgrades/market/buy", headers=auth(1))
    cards = {
        c["id"]: c for c in (await client.get("/api/upgrades", headers=auth(1))).json()["cards"]
    }
    assert len(cards) == 14
    assert cards["market"]["level"] == 1
    assert cards["market"]["next_cost"] == 155
    assert cards["market"]["next_gain"] == 13
    assert cards["market"]["total_effect"] == 12
    assert cards["bank"]["level"] == 0
