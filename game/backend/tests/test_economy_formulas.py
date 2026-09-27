from datetime import UTC, date, datetime, timedelta

from app.game import economy as e
from app.game.cards import CARDS_BY_ID

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def test_levels():
    assert e.level_for(0) == 1
    assert e.level_for(4_999) == 1
    assert e.level_for(5_000) == 2
    assert e.level_for(1_000_000_000) == 10
    assert e.level_for(10**12) == 10
    assert e.level_bounds(1) == (0, 5_000)
    assert e.level_bounds(10) == (1_000_000_000, None)


def test_tap_power_and_energy_max():
    assert e.tap_power(1, 0) == 1
    assert e.tap_power(3, 2) == 5
    assert e.energy_max(0) == 1000
    assert e.energy_max(2) == 2000


def test_energy_regen_keeps_fractions():
    energy, at = e.regen_energy(0, 1000, T0, T0 + timedelta(seconds=0.7))
    assert energy == 1  # 1.4 units -> 1 whole unit
    assert at == T0 + timedelta(seconds=0.5)
    energy, at = e.regen_energy(energy, 1000, at, T0 + timedelta(seconds=1.0))
    assert energy == 2  # the 0.2s remainder was not lost


def test_energy_regen_caps_at_max():
    assert e.regen_energy(990, 1000, T0, T0 + timedelta(hours=1)) == (1000, T0 + timedelta(hours=1))
    assert e.regen_energy(1000, 1000, T0, T0 + timedelta(seconds=5)) == (
        1000,
        T0 + timedelta(seconds=5),
    )


def test_allowed_taps_limited_by_rate_and_energy():
    assert e.allowed_taps(100, 1000, T0, T0 + timedelta(seconds=10)) == 100
    assert e.allowed_taps(1000, 1000, T0, T0 + timedelta(seconds=1)) == 15  # autoclicker
    assert e.allowed_taps(100, 40, T0, T0 + timedelta(seconds=10)) == 40  # energy
    assert e.allowed_taps(5000, 5000, None, T0) == 900  # first batch: 60s window
    assert e.allowed_taps(5000, 5000, T0, T0 + timedelta(hours=1)) == 900


def test_passive_accrual_is_lossless_with_frequent_syncs():
    last = T0
    total = 0
    for minute in range(10, 61, 10):
        coins, last = e.accrue_passive(12, last, T0 + timedelta(minutes=minute), 3)
        total += coins
    assert total == 12


def test_passive_accrual_respects_offline_cap():
    coins, last = e.accrue_passive(12, T0, T0 + timedelta(hours=5), 3)
    assert coins == 36
    assert last == T0 + timedelta(hours=5)
    coins, _ = e.accrue_passive(12, T0, T0 + timedelta(hours=5), 12)
    assert coins == 60
    assert e.accrue_passive(0, T0, T0 + timedelta(hours=1), 3) == (0, T0 + timedelta(hours=1))


def test_vip_and_offline_cap():
    assert e.effective_income(100, vip_active=True) == 150
    assert e.offline_cap_hours(False, False) == 3
    assert e.offline_cap_hours(True, False) == 12
    assert e.offline_cap_hours(False, True) == 12


def test_card_costs_and_gains_match_plan():
    market = CARDS_BY_ID["market"]
    assert [market.cost(n) for n in (1, 2, 3)] == [100, 155, 240]
    assert [market.gain(n) for n in (1, 2, 3)] == [12, 13, 15]
    assert CARDS_BY_ID["barracks"].cost(2) == 480
    assert CARDS_BY_ID["barracks"].gain(5) == 300  # +3% per level, in basis points
    assert CARDS_BY_ID["multitap"].cost(3) == 2000
    assert CARDS_BY_ID["multitap"].max_level == 10
    assert CARDS_BY_ID["tech_park"].max_level == 20


def test_daily_streak():
    d = date(2026, 1, 1)
    first = e.daily_claim(0, None, d)
    assert (first.reward, first.streak) == (500, 1)
    assert e.daily_claim(1, d, d) is None
    second = e.daily_claim(1, d, d + timedelta(days=1))
    assert (second.reward, second.streak) == (1000, 2)
    reset = e.daily_claim(5, d, d + timedelta(days=2))
    assert (reset.reward, reset.streak) == (500, 1)
    assert e.daily_claim(10, d, d + timedelta(days=1)).reward == 500_000


def test_combo_reward():
    assert e.combo_reward(0) == 20_000
    assert e.combo_reward(5_000) == 50_000


def test_bp_to_mult():
    assert e.bp_to_mult(0) == 1.0
    assert e.bp_to_mult(1500) == 1.15
