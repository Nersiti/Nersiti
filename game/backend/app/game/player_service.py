import random
import re
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TgIdentity
from app.game import economy
from app.game.cards import CARDS, CARDS_BY_ID
from app.game.errors import GameError
from app.models import DailyCombo, User, UserCombo, UserUpgrade

REF_RE = re.compile(r"^r_(\d{1,20})$")


def utcnow() -> datetime:
    return datetime.now(UTC)


def parse_referrer(start_param: str | None, self_id: int) -> int | None:
    if not start_param:
        return None
    m = REF_RE.match(start_param)
    if not m:
        return None
    ref_id = int(m.group(1))
    return None if ref_id == self_id else ref_id


async def upsert_user(
    session: AsyncSession, identity: TgIdentity, start_param: str | None
) -> tuple[User, bool]:
    """Creates the user on first visit, refreshes profile fields otherwise.

    Returns (locked user row, created flag).
    """
    now = utcnow()
    inserted = await session.execute(
        insert(User)
        .values(
            id=identity.id,
            first_name=identity.first_name[:128],
            last_name=identity.last_name[:128] if identity.last_name else None,
            username=identity.username,
            language_code=identity.language_code,
            is_premium=identity.is_premium,
            photo_url=identity.photo_url,
            coins=economy.START_COINS,
            energy=economy.ENERGY_BASE_MAX,
            energy_max=economy.ENERGY_BASE_MAX,
            energy_updated_at=now,
            last_passive_at=now,
        )
        .on_conflict_do_nothing(index_elements=[User.id])
        .returning(User.id)
    )
    created = inserted.scalar_one_or_none() is not None

    user = (
        await session.execute(select(User).where(User.id == identity.id).with_for_update())
    ).scalar_one()

    if created:
        referrer_id = parse_referrer(start_param, user.id)
        if referrer_id is not None and await session.get(User, referrer_id) is not None:
            user.referrer_id = referrer_id
    else:
        user.first_name = identity.first_name[:128]
        user.last_name = identity.last_name[:128] if identity.last_name else None
        user.username = identity.username
        user.language_code = identity.language_code
        user.is_premium = identity.is_premium
        user.photo_url = identity.photo_url
    user.last_seen_at = now
    return user, created


# --- Economy -----------------------------------------------------------------------


def is_vip(user: User, now: datetime) -> bool:
    return user.vip_until is not None and user.vip_until > now


def has_autocollector(user: User, now: datetime) -> bool:
    return user.offline_cap_until is not None and user.offline_cap_until > now


def credit(user: User, amount: int) -> None:
    """Adds earned coins (counts towards level)."""
    if amount <= 0:
        return
    user.coins += amount
    user.total_earned += amount
    user.level = max(user.level, economy.level_for(user.total_earned))


def sync_user(user: User, now: datetime) -> int:
    """Applies energy regeneration and passive income. Returns passive coins credited."""
    # Rewards granted in bulk SQL (season end) bypass credit(), so re-derive the level.
    user.level = max(user.level, economy.level_for(user.total_earned))
    user.last_seen_at = now
    user.energy, user.energy_updated_at = economy.regen_energy(
        user.energy, user.energy_max, user.energy_updated_at, now
    )
    vip = is_vip(user, now)
    cap = economy.offline_cap_hours(vip, has_autocollector(user, now))
    coins, user.last_passive_at = economy.accrue_passive(
        economy.effective_income(user.income_per_hour, vip), user.last_passive_at, now, cap
    )
    if coins:
        credit(user, coins)
        user.passive_earned_total += coins
    return coins


def tap(user: User, requested: int, now: datetime) -> int:
    """Consumes energy for taps (call sync_user first). Returns coins earned."""
    if requested <= 0:
        return 0
    allowed = economy.allowed_taps(requested, user.energy, user.last_tap_at, now)
    window = (
        economy.TAP_WINDOW_CAP_SECONDS
        if user.last_tap_at is None
        else min(economy.TAP_WINDOW_CAP_SECONDS, (now - user.last_tap_at).total_seconds())
    )
    if requested > economy.MAX_TAPS_PER_SEC * window * 1.5 + 5:
        user.suspicion += 1
    user.energy -= allowed
    user.last_tap_at = now
    earned = allowed * economy.tap_power(user.level, user.multitap_level)
    credit(user, earned)
    return earned


def claim_daily(user: User, today: date) -> int:
    result = economy.daily_claim(user.daily_streak, user.daily_last_date, today)
    if result is None:
        raise GameError("already_claimed", 409)
    user.daily_streak = result.streak
    user.daily_last_date = today
    credit(user, result.reward)
    return result.reward


async def upgrade_levels(session: AsyncSession, user_id: int) -> dict[str, int]:
    rows = await session.execute(
        select(UserUpgrade.card_id, UserUpgrade.level).where(UserUpgrade.user_id == user_id)
    )
    return dict(rows.all())


async def buy_upgrade(session: AsyncSession, user: User, card_id: str, today: date) -> dict:
    """User row must be locked and synced. Returns {"level", "cost", "combo_reward"}."""
    card = CARDS_BY_ID.get(card_id)
    if card is None:
        raise GameError("unknown_card", 404)
    row = await session.get(UserUpgrade, (user.id, card_id))
    level = row.level if row else 0
    if level >= card.max_level:
        raise GameError("max_level")
    new_level = level + 1
    cost = card.cost(new_level)
    if user.coins < cost:
        raise GameError("not_enough_coins")

    user.coins -= cost
    gain = card.gain(new_level)
    if card.effect == "income":
        user.income_per_hour += gain
    elif card.effect == "attack_bp":
        user.attack_bonus_bp += gain
    elif card.effect == "defense_bp":
        user.defense_bonus_bp += gain
    elif card.effect == "multitap":
        user.multitap_level += gain
    elif card.effect == "battery":
        user.energy_max += economy.BATTERY_ENERGY_PER_LEVEL * gain

    if row is None:
        session.add(UserUpgrade(user_id=user.id, card_id=card_id, level=new_level))
    else:
        row.level = new_level

    reward = await register_combo_progress(session, user, card_id, today)
    return {"level": new_level, "cost": cost, "combo_reward": reward}


# --- Daily combo -------------------------------------------------------------------


async def get_or_create_combo(session: AsyncSession, day: date) -> list[str]:
    row = await session.get(DailyCombo, day)
    if row is None:
        ids = random.sample([c.id for c in CARDS], economy.COMBO_SIZE)
        await session.execute(
            insert(DailyCombo).values(day=day, card_ids=ids).on_conflict_do_nothing()
        )
        row = await session.get(DailyCombo, day)
    return list(row.card_ids)


async def register_combo_progress(
    session: AsyncSession, user: User, card_id: str, day: date
) -> int:
    combo_ids = await get_or_create_combo(session, day)
    if card_id not in combo_ids:
        return 0
    progress = await session.get(UserCombo, (user.id, day))
    if progress is None:
        progress = UserCombo(user_id=user.id, day=day, found=[], claimed=False)
        session.add(progress)
    if card_id not in progress.found:
        progress.found = [*progress.found, card_id]
    if len(progress.found) >= economy.COMBO_SIZE and not progress.claimed:
        progress.claimed = True
        reward = economy.combo_reward(user.income_per_hour)
        credit(user, reward)
        return reward
    return 0


async def combo_status(session: AsyncSession, user: User, day: date) -> dict:
    await get_or_create_combo(session, day)
    progress = await session.get(UserCombo, (user.id, day))
    found = list(progress.found) if progress else []
    return {
        "found": found,
        "total": economy.COMBO_SIZE,
        "reward": economy.combo_reward(user.income_per_hour),
        "claimed": bool(progress and progress.claimed),
    }
