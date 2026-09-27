from functools import lru_cache

from babel import Locale
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import City

# Default country suggestion by Telegram language code.
LANG_TO_COUNTRY = {
    "ru": "RU", "uk": "UA", "be": "BY", "kk": "KZ", "uz": "UZ", "ky": "KG", "tg": "TJ",
    "hy": "AM", "az": "AZ", "ka": "GE", "tk": "TM", "de": "DE", "fr": "FR", "es": "ES",
    "it": "IT", "pt": "BR", "tr": "TR", "fa": "IR", "ar": "EG", "id": "ID", "pl": "PL",
    "vi": "VN", "hi": "IN", "ms": "MY", "nl": "NL", "ko": "KR", "ja": "JP", "zh": "CN",
    "he": "IL", "sr": "RS", "bg": "BG", "cs": "CZ", "hu": "HU", "el": "GR", "ro": "RO",
    "en": "US",
}  # fmt: skip

_country_codes: list[str] | None = None


@lru_cache(maxsize=4)
def _territories(lang: str) -> dict[str, str]:
    return dict(Locale(lang).territories)


def country_name(code: str, lang: str) -> str:
    return _territories(lang).get(code) or code


def city_name(city: City, lang: str) -> str:
    return city.name_ru if lang == "ru" and city.name_ru else city.name_en


def suggest_country(language_code: str | None) -> str | None:
    if not language_code:
        return None
    return LANG_TO_COUNTRY.get(language_code.split("-")[0].lower())


async def country_codes(session: AsyncSession) -> list[str]:
    """Countries that have at least one playable city (cached for the process lifetime)."""
    global _country_codes
    if _country_codes is None:
        rows = await session.execute(
            select(City.country_code).where(City.sectors_count > 0).distinct()
        )
        codes = sorted(r[0] for r in rows)
        if not codes:
            return []  # world not built yet: do not cache
        _country_codes = codes
    return _country_codes


def reset_cache() -> None:
    global _country_codes
    _country_codes = None


async def list_countries(session: AsyncSession, lang: str) -> list[dict]:
    items = [{"code": c, "name": country_name(c, lang)} for c in await country_codes(session)]
    items.sort(key=lambda x: x["name"])
    return items


async def search_cities(
    session: AsyncSession, query: str, lang: str, country: str | None, limit: int = 20
) -> list[dict]:
    q = query.strip().lower()
    q = q.replace("%", "").replace("_", "")
    if len(q) < 2:
        return []
    stmt = (
        select(City)
        .where(
            City.sectors_count > 0,
            or_(func.lower(City.name_ru).like(f"{q}%"), func.lower(City.name_en).like(f"{q}%")),
        )
        .order_by(City.population.desc())
        .limit(limit)
    )
    if country:
        stmt = stmt.where(City.country_code == country)
    cities = (await session.execute(stmt)).scalars().all()
    return [city_to_dict(c, lang) for c in cities]


def city_to_dict(city: City, lang: str) -> dict:
    return {
        "id": city.id,
        "name": city_name(city, lang),
        "country_code": city.country_code,
        "country_name": country_name(city.country_code, lang),
        "population": city.population,
        "lat": city.lat,
        "lng": city.lng,
        "sectors_count": city.sectors_count,
    }
