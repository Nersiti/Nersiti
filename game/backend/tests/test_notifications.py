import json
from datetime import UTC, datetime, timedelta

import h3
import pytest
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from sqlalchemy import update

from app.game import player_service
from app.models import Clan, User
from app.notify import QUEUE_KEY, enqueue, webapp_button
from app.redis_client import get_redis
from app.worker import notifications
from tests.helpers import auth, login, seed_world

T0 = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
KAZAN_CENTER = h3.latlng_to_cell(55.78874, 49.12214, 6)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock(monkeypatch) -> Clock:
    c = Clock()
    monkeypatch.setattr(player_service, "utcnow", c)
    return c


async def queued() -> list[dict]:
    return [json.loads(x) for x in await get_redis().lrange(QUEUE_KEY, 0, -1)]


async def onboard(client, db, user_id, city_id, coins=100_000):
    await login(client, user_id)
    await client.post(
        "/api/onboarding", json={"country_code": "RU", "city_id": city_id}, headers=auth(user_id)
    )
    await db.execute(update(User).where(User.id == user_id).values(coins=coins))
    await db.commit()


async def test_personal_messages_are_capped_per_day():
    results = [await enqueue(1, f"m{i}", user_id=1, now=T0) for i in range(7)]
    assert results == [True] * 5 + [False] * 2
    assert await enqueue(1, "tomorrow", user_id=1, now=T0 + timedelta(days=1)) is True
    assert await enqueue(-100, "group message, no cap") is True
    assert len(await queued()) == 7


async def test_sender_sends_with_button(bot_session):
    await enqueue(5, "hello", button=webapp_button("Play"), user_id=5)
    raw = await get_redis().lpop(QUEUE_KEY)
    assert await notifications.Sender(bot_session_bot()).process(raw) == "sent"
    [sent] = bot_session.of_type("SendMessage")
    assert sent.chat_id == 5
    assert sent.reply_markup.inline_keyboard[0][0].web_app.url == "https://game.test/"


def bot_session_bot():
    from app.bot.instance import get_bot

    return get_bot()


async def test_sender_requeues_on_flood_and_disables_blocked_users(
    client, db, bot_session, monkeypatch
):
    await login(client, 7)

    async def no_sleep(_):
        return None

    monkeypatch.setattr(notifications.asyncio, "sleep", no_sleep)

    def flood(method):
        raise TelegramRetryAfter(method=method, message="Too Many Requests", retry_after=3)

    bot_session.responses["SendMessage"] = flood
    await enqueue(7, "x", user_id=7)
    raw = await get_redis().lpop(QUEUE_KEY)
    assert await notifications.Sender(bot_session_bot()).process(raw) == "retry"
    assert len(await queued()) == 1  # back at the head of the queue

    def blocked(method):
        raise TelegramForbiddenError(
            method=method, message="Forbidden: bot was blocked by the user"
        )

    bot_session.responses["SendMessage"] = blocked
    raw = await get_redis().lpop(QUEUE_KEY)
    assert await notifications.Sender(bot_session_bot()).process(raw) == "blocked"
    user = await db.get(User, 7)
    await db.refresh(user)
    assert user.notify_enabled is False


async def test_sector_loss_summary(client, db, clock):
    ids = await seed_world(db)
    await onboard(client, db, 1, ids["kazan"])  # holds the sector
    await onboard(client, db, 2, ids["kazan"])  # clan-mate active in the last 24h
    await onboard(client, db, 3, ids["kazan"])  # attacker
    enemy = Clan(kind="channel", tg_chat_id=-5, title="Враги", color="#000000")
    db.add(enemy)
    await db.commit()
    await db.execute(update(User).where(User.id == 3).values(clan_id=enemy.id))
    await db.commit()
    other_sector = next(c for c in h3.grid_disk(KAZAN_CENTER, 1) if c != KAZAN_CENTER)

    r = await client.post(
        f"/api/sector/{KAZAN_CENTER}/action", json={"amount": 1000}, headers=auth(1)
    )
    assert r.status_code == 200
    r = await client.post(
        f"/api/sector/{other_sector}/action", json={"amount": 500}, headers=auth(2)
    )
    assert r.status_code == 200
    clock.now += timedelta(minutes=1)
    r = await client.post(
        f"/api/sector/{KAZAN_CENTER}/action", json={"amount": 5000}, headers=auth(3)
    )
    assert r.json()["result"]["flipped"] is True
    await get_redis().delete(QUEUE_KEY)

    now = clock.now + timedelta(minutes=5)
    count = await notifications.sector_loss_summary(db, now)
    messages = {m["chat_id"]: m for m in await queued()}
    assert count == 2
    assert set(messages) == {1, 2}
    assert "Потеряно: 1 (Казань)" in messages[1]["text"]
    assert "Враги" in messages[1]["text"]
    assert "потерял секторов: 1" in messages[2]["text"]
    assert messages[1]["button"]["web_app"] == "https://game.test/"

    # The same flips are not reported twice.
    assert await notifications.sector_loss_summary(db, now + timedelta(minutes=30)) == 0


async def test_group_digest(client, db, clock):
    ids = await seed_world(db)
    await onboard(client, db, 1, ids["kazan"])
    group = Clan(kind="group", tg_chat_id=-4242, title="Чат 11Б", color="#123456", owner_user_id=1)
    db.add(group)
    await db.commit()
    await db.execute(update(User).where(User.id == 1).values(clan_id=group.id))
    await db.commit()
    await client.post(f"/api/sector/{KAZAN_CENTER}/action", json={"amount": 1000}, headers=auth(1))

    assert await notifications.group_digests(db, clock.now + timedelta(minutes=10)) == 1
    [msg] = await queued()
    assert msg["chat_id"] == -4242
    assert "Захвачено секторов: 1" in msg["text"]
    assert msg["button"]["url"] == f"https://t.me/test_bot?startapp=c_{group.id}"
    # Nothing happened in the next window: no digest.
    assert await notifications.group_digests(db, clock.now + timedelta(hours=4)) == 0


async def test_storage_full_reminder_once_a_day(client, db, clock):
    ids = await seed_world(db)
    await onboard(client, db, 1, ids["kazan"])
    await onboard(client, db, 2, ids["kazan"])
    await db.execute(
        update(User)
        .where(User.id.in_([1, 2]))
        .values(income_per_hour=100, last_seen_at=T0 - timedelta(hours=3, minutes=30))
    )
    await db.execute(update(User).where(User.id == 2).values(notify_enabled=False))
    await db.commit()

    assert await notifications.storage_full_reminders(db, T0) == 1
    [msg] = await queued()
    assert msg["chat_id"] == 1
    assert "300" in msg["text"]
    assert await notifications.storage_full_reminders(db, T0 + timedelta(minutes=10)) == 0


async def test_settings_toggle(client, clock):
    await login(client, 1)
    res = await client.patch("/api/settings", json={"notify_enabled": False}, headers=auth(1))
    assert res.json()["state"]["notify_enabled"] is False


async def test_bot_settings_command(client, db, bot_session):
    await login(client, 1)
    update_msg = {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "date": 1700000000,
            "chat": {"id": 1, "type": "private"},
            "from": {"id": 1, "is_bot": False, "first_name": "A", "language_code": "ru"},
            "text": "/settings",
            "entities": [{"type": "bot_command", "offset": 0, "length": 9}],
        },
    }
    headers = {"X-Telegram-Bot-Api-Secret-Token": "test-secret"}
    await client.post("/tg/webhook", json=update_msg, headers=headers)
    [sent] = bot_session.of_type("SendMessage")
    assert "включены" in sent.text

    callback = {
        "update_id": 2,
        "callback_query": {
            "id": "c",
            "chat_instance": "ci",
            "from": {"id": 1, "is_bot": False, "first_name": "A", "language_code": "ru"},
            "data": "settings:notify",
        },
    }
    await client.post("/tg/webhook", json=callback, headers=headers)
    user = await db.get(User, 1)
    await db.refresh(user)
    assert user.notify_enabled is False
