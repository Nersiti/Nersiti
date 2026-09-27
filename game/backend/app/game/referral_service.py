"""Referral rewards (PLAN.md, section B, "Рефералы")."""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.game import economy, player_service
from app.game.errors import GameError
from app.models import Referral, User


def invite_link(user_id: int) -> str:
    return f"https://t.me/{get_settings().bot_username}?startapp=r_{user_id}"


async def _credit_by_id(session: AsyncSession, user_id: int, amount: int) -> None:
    """Credits a user that is not locked in this transaction (atomic UPDATE)."""
    await session.execute(
        update(User)
        .where(User.id == user_id)
        .values(coins=User.coins + amount, total_earned=User.total_earned + amount)
    )


async def on_registered(session: AsyncSession, user: User) -> None:
    """Called once, right after a new user with a valid referrer was created."""
    if user.referrer_id is None:
        return
    session.add(Referral(invitee_id=user.id, inviter_id=user.referrer_id, passive_snapshot=0))
    player_service.credit(user, economy.REF_INVITEE_BONUS)
    bonus = economy.REF_INVITER_PREMIUM_BONUS if user.is_premium else economy.REF_INVITER_BONUS
    await _credit_by_id(session, user.referrer_id, bonus)


async def check_level_bonus(session: AsyncSession, user: User) -> bool:
    """Pays the inviter once the invitee reaches level 3."""
    if user.referrer_id is None or user.level < economy.REF_LEVEL_FOR_BONUS:
        return False
    result = await session.execute(
        update(Referral)
        .where(Referral.invitee_id == user.id, Referral.l3_rewarded.is_(False))
        .values(l3_rewarded=True)
        .returning(Referral.inviter_id)
    )
    inviter_id = result.scalar_one_or_none()
    if inviter_id is None:
        return False
    await _credit_by_id(session, inviter_id, economy.REF_LEVEL3_BONUS)
    return True


async def pending_mentor_bonus(session: AsyncSession, inviter_id: int) -> int:
    rows = (
        await session.execute(
            select(User.passive_earned_total, Referral.passive_snapshot)
            .join(Referral, Referral.invitee_id == User.id)
            .where(Referral.inviter_id == inviter_id)
        )
    ).all()
    return economy.mentor_bonus(sum(total - snap for total, snap in rows))


async def summary(session: AsyncSession, user: User, now: datetime) -> dict:
    invitees = (
        await session.execute(
            select(User.id, User.first_name, User.level, User.is_premium)
            .join(Referral, Referral.invitee_id == User.id)
            .where(Referral.inviter_id == user.id)
            .order_by(Referral.created_at.desc())
            .limit(50)
        )
    ).all()
    count = len(invitees)
    next_claim = None
    if user.ref_claimed_at is not None:
        elapsed = (now - user.ref_claimed_at).total_seconds()
        if elapsed < economy.REF_CLAIM_INTERVAL_SECONDS:
            next_claim = int(economy.REF_CLAIM_INTERVAL_SECONDS - elapsed)
    return {
        "link": invite_link(user.id),
        "count": count,
        "invitees": [
            {"id": r.id, "first_name": r.first_name, "level": r.level, "is_premium": r.is_premium}
            for r in invitees
        ],
        "pending_bonus": await pending_mentor_bonus(session, user.id),
        "claim_in_seconds": next_claim,
        "rewards": {
            "invitee": economy.REF_INVITEE_BONUS,
            "inviter": economy.REF_INVITER_BONUS,
            "inviter_premium": economy.REF_INVITER_PREMIUM_BONUS,
            "level3": economy.REF_LEVEL3_BONUS,
            "mentor_share": economy.REF_MENTOR_SHARE,
        },
    }


async def claim_mentor_bonus(session: AsyncSession, user: User, now: datetime) -> int:
    """User row must be locked."""
    if (
        user.ref_claimed_at is not None
        and (now - user.ref_claimed_at).total_seconds() < economy.REF_CLAIM_INTERVAL_SECONDS
    ):
        raise GameError("claim_too_soon", 429)
    refs = (
        (
            await session.execute(
                select(Referral).where(Referral.inviter_id == user.id).with_for_update()
            )
        )
        .scalars()
        .all()
    )
    totals = dict(
        (
            await session.execute(
                select(User.id, User.passive_earned_total).where(
                    User.id.in_([r.invitee_id for r in refs])
                )
            )
        ).all()
    )
    delta = 0
    for ref in refs:
        current = totals.get(ref.invitee_id, ref.passive_snapshot)
        delta += current - ref.passive_snapshot
        ref.passive_snapshot = current
    reward = economy.mentor_bonus(delta)
    user.ref_claimed_at = now
    player_service.credit(user, reward)
    return reward
