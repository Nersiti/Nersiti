from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthError, TgIdentity, dev_identity, validate_init_data
from app.config import get_settings
from app.db import get_session
from app.models import User
from app.redis_client import rate_limit


async def get_identity(authorization: str | None = Header(default=None)) -> TgIdentity:
    settings = get_settings()
    scheme, _, value = (authorization or "").partition(" ")
    try:
        if scheme == "tma" and value:
            return validate_init_data(value, settings.bot_token, settings.init_data_ttl_seconds)
        if scheme == "dev" and settings.dev_mode:
            return dev_identity(value)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    raise HTTPException(status_code=401, detail="unauthorized")


async def _load_user(session: AsyncSession, user_id: int, lock: bool) -> User:
    stmt = select(User).where(User.id == user_id)
    if lock:
        stmt = stmt.with_for_update()
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="no_session")
    if user.banned:
        raise HTTPException(status_code=403, detail="banned")
    return user


async def get_user(
    identity: TgIdentity = Depends(get_identity),
    session: AsyncSession = Depends(get_session),
) -> User:
    return await _load_user(session, identity.id, lock=False)


async def get_user_locked(
    identity: TgIdentity = Depends(get_identity),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Loads the user with SELECT ... FOR UPDATE for state-changing endpoints."""
    return await _load_user(session, identity.id, lock=True)


def limit(name: str, per_window: int, window_seconds: int):
    """Per-user rate limit dependency."""

    async def dependency(identity: TgIdentity = Depends(get_identity)) -> None:
        if not await rate_limit(f"{name}:{identity.id}", per_window, window_seconds):
            raise HTTPException(status_code=429, detail="too_many_requests")

    return dependency
