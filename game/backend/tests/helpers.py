import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlencode


def make_init_data(
    user_id: int,
    first_name: str = "Test",
    *,
    auth_date: int | None = None,
    start_param: str | None = None,
    language_code: str = "ru",
    is_premium: bool = False,
    token: str | None = None,
) -> str:
    """Builds initData signed exactly like Telegram does."""
    token = token or os.environ["BOT_TOKEN"]
    user = {"id": user_id, "first_name": first_name, "language_code": language_code}
    if is_premium:
        user["is_premium"] = True
    fields = {
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": "AAH-test",
        "user": json.dumps(user, separators=(",", ":"), ensure_ascii=False),
    }
    if start_param:
        fields["start_param"] = start_param
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def auth(user_id: int, **kwargs) -> dict[str, str]:
    return {"Authorization": f"tma {make_init_data(user_id, **kwargs)}"}


async def login(client, user_id: int, **kwargs) -> dict:
    body = kwargs.pop("body", {})
    res = await client.post("/api/session", json=body, headers=auth(user_id, **kwargs))
    assert res.status_code == 200, res.text
    return res.json()


async def seed_world(db) -> dict[str, int]:
    """Inserts a tiny world: Moscow (capital), Kazan, Khimki and a Turkish Kazan."""
    from app.game import world_service
    from app.game.world import CityIn, generate_sectors
    from app.models import City, Sector

    cities = [
        CityIn(524901, "Moscow", "Москва", "RU", 55.75204, 37.61781, 10381222, True, "48"),
        CityIn(551487, "Kazan", "Казань", "RU", 55.78874, 49.12214, 1243500, False, "73"),
        CityIn(550280, "Khimki", "Химки", "RU", 55.9001, 37.42848, 239967, False, "47"),
        CityIn(743615, "Kazan", "Казан", "TR", 40.23167, 32.68389, 23889, False, "68"),
    ]
    kept, sectors = generate_sectors(cities)
    for c in kept:
        db.add(
            City(
                id=c.id, name_en=c.name_en, name_ru=c.name_ru, country_code=c.country_code,
                lat=c.lat, lng=c.lng, population=c.population, is_capital=c.is_capital,
                sectors_count=c.sectors_count,
            )
        )  # fmt: skip
    await db.flush()
    for s in sectors:
        db.add(Sector(h3=s.h3, city_id=s.city_id, lat=s.lat, lng=s.lng, value=s.value))
    await db.commit()
    world_service.reset_cache()
    return {"moscow": 524901, "kazan": 551487, "khimki": 550280, "kazan_tr": 743615}
