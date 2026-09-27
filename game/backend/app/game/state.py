"""Serializes the player's state for the Mini App."""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.game import world_service
from app.i18n import pick_lang
from app.models import City, User


async def build_state(session: AsyncSession, user: User) -> dict:
    lang = pick_lang(user.language_code)
    city = await session.get(City, user.city_id) if user.city_id else None
    return {
        "user": {
            "id": user.id,
            "first_name": user.first_name,
            "username": user.username,
            "photo_url": user.photo_url,
            "lang": lang,
            "is_premium": user.is_premium,
        },
        "onboarded": city is not None,
        "country_code": user.country_code,
        "country_name": (
            world_service.country_name(user.country_code, lang) if user.country_code else None
        ),
        "city": world_service.city_to_dict(city, lang) if city else None,
        "coins": user.coins,
        "server_time": datetime.now(UTC).isoformat(),
    }


def build_config() -> dict:
    settings = get_settings()
    return {
        "game_name": settings.game_name,
        "bot_username": settings.bot_username,
    }
