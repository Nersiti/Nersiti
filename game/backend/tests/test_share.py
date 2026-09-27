from datetime import UTC, datetime, timedelta

import h3
import pytest
from aiogram.types import PreparedInlineMessage
from sqlalchemy import update

from app.game import player_service, share_service
from app.images import map_snapshot
from app.models import Clan, User
from app.notify import QUEUE_KEY
from app.redis_client import get_redis
from app.worker import notifications
from tests.helpers import auth, login, seed_world

T0 = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
KAZAN_CENTER = h3.latlng_to_cell(55.78874, 49.12214, 6)


@pytest.fixture(autouse=True)
def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(player_service, "utcnow", lambda: T0)
    monkeypatch.setattr(share_service, "CACHE_DIR", tmp_path / "cards")
    monkeypatch.setattr(map_snapshot, "SNAPSHOT_DIR", tmp_path / "snapshots")


async def onboard(client, user_id, city_id):
    await login(client, user_id)
    await client.post(
        "/api/onboarding", json={"country_code": "RU", "city_id": city_id}, headers=auth(user_id)
    )


async def test_share_links_and_signed_image(client, db):
    ids = await seed_world(db)
    await onboard(client, 1, ids["kazan"])
    links = (await client.get("/api/share/links?kind=me", headers=auth(1))).json()
    assert links["link"] == "https://t.me/test_bot?startapp=r_1"
    assert links["story_url"].startswith("https://game.test/api/share/img/1-me-story-")

    path = links["story_url"].replace("https://game.test", "")
    res = await client.get(path)  # public: no auth header
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert res.content[:8] == b"\x89PNG\r\n\x1a\n"

    tampered = path[:-6] + "000000.png"
    assert (await client.get(tampered)).status_code == 404
    assert (await client.get("/api/share/img/2-me-story-abcdef.png")).status_code == 404


async def test_clan_share_uses_clan_link(client, db):
    ids = await seed_world(db)
    await onboard(client, 1, ids["kazan"])
    clan = Clan(kind="channel", tg_chat_id=-1, title="Канал", color="#ff0000")
    db.add(clan)
    await db.commit()
    await db.execute(update(User).where(User.id == 1).values(clan_id=clan.id))
    await db.commit()
    links = (await client.get("/api/share/links?kind=clan", headers=auth(1))).json()
    assert links["link"] == f"https://t.me/test_bot?startapp=c_{clan.id}"
    post = links["post_url"].replace("https://game.test", "")
    assert (await client.get(post)).status_code == 200


async def test_prepare_message(client, db, bot_session):
    await login(client, 1)
    bot_session.responses["SavePreparedInlineMessage"] = PreparedInlineMessage(
        id="prep-1", expiration_date=int((T0 + timedelta(hours=1)).timestamp())
    )
    res = await client.post("/api/share/prepare", json={"kind": "me"}, headers=auth(1))
    assert res.json() == {"id": "prep-1"}
    [call] = bot_session.of_type("SavePreparedInlineMessage")
    assert call.user_id == 1
    assert call.result.photo_url.startswith("https://game.test/api/share/img/1-me-post-")
    assert call.result.reply_markup.inline_keyboard[0][0].url.endswith("startapp=r_1")
    assert call.allow_group_chats and call.allow_channel_chats


async def test_weekly_results_and_snapshot(client, db, monkeypatch):
    ids = await seed_world(db)
    await onboard(client, 1, ids["kazan"])
    group = Clan(kind="group", tg_chat_id=-77, title="Чат", color="#00ff00", owner_user_id=1)
    db.add(group)
    await db.commit()
    await db.execute(update(User).where(User.id == 1).values(clan_id=group.id, coins=10_000))
    await db.commit()
    res = await client.post(
        f"/api/sector/{KAZAN_CENTER}/action", json={"amount": 1000}, headers=auth(1)
    )
    assert res.status_code == 200

    assert await notifications.weekly_group_results(db, T0 + timedelta(days=1)) == 1
    raw = await get_redis().lrange(QUEUE_KEY, 0, -1)
    assert "Лучший боец: Test" in raw[0]

    path = await map_snapshot.save_snapshot(db, 1, T0)
    assert path.read_bytes()[:4] == b"\x89PNG"
