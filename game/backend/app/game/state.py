"""Serializes the player's state for the Mini App."""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.i18n import pick_lang
from app.models import User


async def build_state(session: AsyncSession, user: User) -> dict:
    return {
        "user": {
            "id": user.id,
            "first_name": user.first_name,
            "username": user.username,
            "photo_url": user.photo_url,
            "lang": pick_lang(user.language_code),
            "is_premium": user.is_premium,
        },
        "coins": user.coins,
        "server_time": datetime.now(UTC).isoformat(),
    }


def build_config() -> dict:
    settings = get_settings()
    return {
        "game_name": settings.game_name,
        "bot_username": settings.bot_username,
    }
