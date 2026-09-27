"""All game-balance constants and pure formulas.

Values come from PLAN.md, section B. Do not change them without updating the plan.
Every function here is pure (no DB, no clock): callers pass `now`.
"""

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta

START_COINS = 1000

# --- Taps & energy ---
ENERGY_BASE_MAX = 1000
ENERGY_REGEN_PER_SEC = 2
MAX_TAPS_PER_SEC = 15
TAP_WINDOW_CAP_SECONDS = 60
BATTERY_ENERGY_PER_LEVEL = 500

# --- Passive income ---
OFFLINE_CAP_HOURS = 3
OFFLINE_CAP_HOURS_EXTENDED = 12  # VIP or "Автосборщик"
VIP_PASSIVE_MULTIPLIER = 1.5

# --- Levels (by total_earned) ---
LEVEL_THRESHOLDS = [
    0, 5_000, 25_000, 100_000, 500_000, 2_000_000, 10_000_000, 50_000_000,
    200_000_000, 1_000_000_000,
]  # fmt: skip
MAX_LEVEL = len(LEVEL_THRESHOLDS)

# --- Daily reward & combo ---
DAILY_REWARDS = [500, 1000, 2500, 5000, 10000, 25000, 50000, 100000, 250000, 500000]
COMBO_MIN_REWARD = 20_000
COMBO_INCOME_HOURS = 10
COMBO_SIZE = 3

ECONOMY_INCOME_GROWTH = 1.12


def level_for(total_earned: int) -> int:
    level = 1
    for i, threshold in enumerate(LEVEL_THRESHOLDS):
        if total_earned >= threshold:
            level = i + 1
    return level


def level_bounds(level: int) -> tuple[int, int | None]:
    """(threshold of the current level, threshold of the next level or None at max)."""
    current = LEVEL_THRESHOLDS[level - 1]
    nxt = LEVEL_THRESHOLDS[level] if level < MAX_LEVEL else None
    return current, nxt


def tap_power(level: int, multitap_level: int) -> int:
    return level + multitap_level


def energy_max(battery_level: int) -> int:
    return ENERGY_BASE_MAX + BATTERY_ENERGY_PER_LEVEL * battery_level


def regen_energy(
    energy: int, max_energy: int, updated_at: datetime, now: datetime
) -> tuple[int, datetime]:
    """Returns (energy now, new updated_at). Only whole energy units are consumed from
    the elapsed time, so the fractional part keeps accumulating."""
    if energy >= max_energy:
        return max_energy, now
    elapsed = max(0.0, (now - updated_at).total_seconds())
    gained = math.floor(elapsed * ENERGY_REGEN_PER_SEC)
    if energy + gained >= max_energy:
        return max_energy, now
    return energy + gained, updated_at + timedelta(seconds=gained / ENERGY_REGEN_PER_SEC)


def allowed_taps(
    requested: int, energy_now: int, last_tap_at: datetime | None, now: datetime
) -> int:
    """Server-side cap: energy and a humanly possible tap rate since the previous batch."""
    if last_tap_at is None:
        window = TAP_WINDOW_CAP_SECONDS
    else:
        window = min(TAP_WINDOW_CAP_SECONDS, max(0.0, (now - last_tap_at).total_seconds()))
    rate_cap = math.floor(MAX_TAPS_PER_SEC * window)
    return max(0, min(requested, energy_now, rate_cap))


def offline_cap_hours(vip_active: bool, autocollector_active: bool) -> int:
    return OFFLINE_CAP_HOURS_EXTENDED if (vip_active or autocollector_active) else OFFLINE_CAP_HOURS


def effective_income(income_per_hour: int, vip_active: bool) -> float:
    return income_per_hour * (VIP_PASSIVE_MULTIPLIER if vip_active else 1.0)


def accrue_passive(
    income_per_hour: float, last_passive_at: datetime, now: datetime, cap_hours: int
) -> tuple[int, datetime]:
    """Returns (coins earned, new last_passive_at).

    Whole coins only; the time behind the fractional remainder is kept so frequent
    syncs never lose income. Time beyond the offline cap is discarded.
    """
    if income_per_hour <= 0:
        return 0, now
    elapsed = max(0.0, (now - last_passive_at).total_seconds())
    cap_seconds = cap_hours * 3600
    if elapsed >= cap_seconds:
        return math.floor(income_per_hour * cap_hours), now
    coins = math.floor(income_per_hour * elapsed / 3600)
    used_seconds = coins * 3600 / income_per_hour
    return coins, last_passive_at + timedelta(seconds=used_seconds)


def card_cost(base_cost: int, growth: float, level_to_buy: int) -> int:
    return round(base_cost * growth ** (level_to_buy - 1))


def economy_income_gain(base_income: int, level_to_buy: int) -> int:
    return round(base_income * ECONOMY_INCOME_GROWTH ** (level_to_buy - 1))


@dataclass(frozen=True)
class DailyClaim:
    reward: int
    streak: int


def daily_claim(streak: int, last_date: date | None, today: date) -> DailyClaim | None:
    """None if already claimed today. Missing a day resets the streak to day 1."""
    if last_date == today:
        return None
    new_streak = streak + 1 if last_date == today - timedelta(days=1) else 1
    return DailyClaim(reward=daily_reward(new_streak), streak=new_streak)


def daily_reward(streak_day: int) -> int:
    return DAILY_REWARDS[min(max(streak_day, 1), len(DAILY_REWARDS)) - 1]


def combo_reward(income_per_hour: int) -> int:
    return max(COMBO_MIN_REWARD, income_per_hour * COMBO_INCOME_HOURS)


def bp_to_mult(bonus_bp: int) -> float:
    return 1 + bonus_bp / 10_000
