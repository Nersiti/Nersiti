"""Sector actions: capture / attack / reinforce (PLAN.md, section B, "Бой").

Lock order in every transaction: user row -> sector row -> city row. This keeps
concurrent attacks on the same sector serialized and deadlock-free.
"""

from datetime import datetime

from sqlalchemy import exists, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.game import economy, player_service
from app.game.clan_service import MILITIA
from app.game.errors import GameError
from app.models import BattleLog, Clan, Sector, User, UserBoost


async def clan_has_sector_in_city(session: AsyncSession, clan_id: int, city_id: int) -> bool:
    return (
        await session.execute(
            select(exists().where(Sector.city_id == city_id, Sector.owner_clan_id == clan_id))
        )
    ).scalar_one()


async def artillery_active(session: AsyncSession, user_id: int, now: datetime) -> bool:
    boost = await session.get(UserBoost, (user_id, "artillery"))
    return boost is not None and boost.until is not None and boost.until > now


def attack_mult(user: User, artillery: bool) -> float:
    mult = economy.bp_to_mult(user.attack_bonus_bp)
    return mult * economy.ARTILLERY_MULTIPLIER if artillery else mult


async def act_on_sector(
    session: AsyncSession, user: User, h3: str, amount: int, now: datetime
) -> dict:
    """User must be locked. Returns the outcome for the client."""
    if user.city_id is None or user.clan_id is None:
        raise GameError("onboarding_required")
    if amount < economy.MIN_ACTION_COINS:
        raise GameError("amount_too_small")
    if (
        user.last_action_at is not None
        and (now - user.last_action_at).total_seconds() < economy.ACTION_COOLDOWN_SECONDS
    ):
        raise GameError("action_cooldown", 429)

    player_service.sync_user(user, now)
    if user.coins < amount:
        raise GameError("not_enough_coins")

    # No autoflush here: the user row is written once, at the explicit flush below.
    with session.no_autoflush:
        sector = (
            await session.execute(select(Sector).where(Sector.h3 == h3).with_for_update())
        ).scalar_one_or_none()
    if sector is None:
        raise GameError("sector_not_found", 404)
    clan = await session.get(Clan, user.clan_id)
    if clan is None:
        raise GameError("onboarding_required")

    own = sector.owner_clan_id == clan.id
    if not own and sector.shield_until is not None and sector.shield_until > now:
        raise GameError("sector_shielded", 403)

    foothold = False
    if sector.city_id != user.city_id:
        if clan.kind == MILITIA:
            raise GameError("militia_home_only", 403)
        foothold = not await clan_has_sector_in_city(session, clan.id, sector.city_id)

    if own:
        power = economy.action_power(amount, economy.bp_to_mult(user.defense_bonus_bp), False)
    else:
        mult = attack_mult(user, await artillery_active(session, user.id, now))
        ad_boost = await session.get(UserBoost, (user.id, "ad_attack"), with_for_update=True)
        if ad_boost is not None and ad_boost.until is not None and ad_boost.until > now:
            mult *= economy.AD_ATTACK_MULTIPLIER
            ad_boost.until = None  # one-shot
        power = economy.action_power(amount, mult, foothold)

    defense_now = economy.decayed_defense(sector.defense, sector.defense_updated_at, now)
    outcome = economy.resolve_battle(
        sector.owner_clan_id, defense_now, sector.value, clan.id, power
    )
    if outcome is None:
        raise GameError("not_enough_power")

    prev_owner = sector.owner_clan_id
    prev_actor = sector.last_actor_id
    user.coins -= amount
    user.last_action_at = now
    user.season_score += power
    if outcome.flipped:
        user.season_score += economy.CAPTURE_SCORE_PER_VALUE * sector.value
        sector.captured_at = now
    sector.owner_clan_id = outcome.owner_clan_id
    sector.defense = outcome.defense
    sector.defense_updated_at = now
    sector.last_actor_id = user.id

    session.add(
        BattleLog(
            created_at=now,
            user_id=user.id,
            clan_id=clan.id,
            sector_h3=sector.h3,
            city_id=sector.city_id,
            action=outcome.action,
            amount=amount,
            power=power,
            flipped=outcome.flipped,
            prev_owner_clan_id=prev_owner,
            prev_actor_id=prev_actor if outcome.flipped else None,
        )
    )
    if outcome.flipped:
        await session.flush()
        await recompute_city_controller(session, sector.city_id)

    return {
        "action": outcome.action,
        "power": power,
        "flipped": outcome.flipped,
        "foothold": foothold,
        "sector": sector_dict(sector, now),
    }


async def recompute_city_controller(session: AsyncSession, city_id: int) -> None:
    """Sets the city's controller to the clan with the largest Σ value (ties keep the
    current controller, then the lowest clan id).

    One atomic UPDATE instead of SELECT ... FOR UPDATE: the users.city_id foreign key
    makes concurrent attack transactions hold KEY SHARE locks on the city row, and
    upgrading those to FOR UPDATE deadlocks. UPDATE of a non-key column takes
    FOR NO KEY UPDATE, which is compatible with KEY SHARE, and it only writes when
    the controller actually changes.
    """
    await session.execute(
        text(
            """
            UPDATE cities SET controller_clan_id = leader.owner_clan_id
            FROM (
                SELECT (
                    SELECT s.owner_clan_id FROM sectors s
                    WHERE s.city_id = :city AND s.owner_clan_id IS NOT NULL
                    GROUP BY s.owner_clan_id
                    ORDER BY SUM(s.value) DESC,
                             COALESCE(s.owner_clan_id = (
                                 SELECT controller_clan_id FROM cities WHERE id = :city
                             ), false) DESC,
                             s.owner_clan_id
                    LIMIT 1
                ) AS owner_clan_id
            ) AS leader
            WHERE cities.id = :city
              AND cities.controller_clan_id IS DISTINCT FROM leader.owner_clan_id
            """
        ),
        {"city": city_id},
    )


def sector_dict(sector: Sector, now: datetime) -> dict:
    shielded = sector.shield_until is not None and sector.shield_until > now
    return {
        "h3": sector.h3,
        "city_id": sector.city_id,
        "value": sector.value,
        "owner_clan_id": sector.owner_clan_id,
        "defense": economy.decayed_defense(sector.defense, sector.defense_updated_at, now),
        "shield_until": sector.shield_until.isoformat() if shielded else None,
        "capture_cost": economy.neutral_capture_cost(sector.value),
    }
