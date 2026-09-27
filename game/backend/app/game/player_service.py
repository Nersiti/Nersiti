import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TgIdentity
from app.game import economy
from app.models import User

REF_RE = re.compile(r"^r_(\d{1,20})$")


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
    now = datetime.now(UTC)
    inserted = await session.execute(
        insert(User)
        .values(
            id=identity.id,
            first_name=identity.first_name[:128],
            last_name=(identity.last_name or None) and identity.last_name[:128],
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
