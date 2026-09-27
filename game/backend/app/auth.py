"""Telegram Mini App authentication.

Every API request carries `Authorization: tma <initData>`; the signature is checked
with the bot token (https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app).
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from aiogram.utils.web_app import safe_parse_webapp_init_data


class AuthError(Exception):
    pass


@dataclass(frozen=True)
class TgIdentity:
    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None
    is_premium: bool = False
    photo_url: str | None = None
    start_param: str | None = None


def validate_init_data(
    init_data: str, bot_token: str, ttl_seconds: int, now: datetime | None = None
) -> TgIdentity:
    try:
        data = safe_parse_webapp_init_data(bot_token, init_data)
    except ValueError as exc:
        raise AuthError("bad_signature") from exc

    now = now or datetime.now(UTC)
    auth_date = data.auth_date
    if auth_date.tzinfo is None:
        auth_date = auth_date.replace(tzinfo=UTC)
    if (now - auth_date).total_seconds() > ttl_seconds:
        raise AuthError("expired")
    if data.user is None:
        raise AuthError("no_user")

    u = data.user
    return TgIdentity(
        id=u.id,
        first_name=u.first_name or "",
        last_name=u.last_name,
        username=u.username,
        language_code=u.language_code,
        is_premium=bool(u.is_premium),
        photo_url=u.photo_url,
        start_param=data.start_param,
    )


def dev_identity(raw_id: str) -> TgIdentity:
    try:
        user_id = int(raw_id)
    except ValueError as exc:
        raise AuthError("bad_dev_id") from exc
    return TgIdentity(id=user_id, first_name=f"Dev {user_id}", language_code="ru")
