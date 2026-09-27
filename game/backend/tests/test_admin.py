from datetime import UTC, datetime

import pytest
from aiogram.types import Gift, Gifts, Sticker
from sqlalchemy import select, update

from app.game import player_service, season_service
from app.models import Clan, DailyCombo, Event, Season, User
from app.notify import QUEUE_KEY
from app.redis_client import get_redis
from tests.helpers import auth, login

T0 = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
WEBHOOK = {"X-Telegram-Bot-Api-Secret-Token": "test-secret"}


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(player_service, "utcnow", lambda: T0)


def command(text: str, user_id: int = 999) -> dict:
    return {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "date": 1700000000,
            "chat": {"id": user_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "Admin", "language_code": "ru"},
            "text": text,
            "entities": [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}],
        },
    }


def callback(data: str, user_id: int = 999) -> dict:
    return {
        "update_id": 2,
        "callback_query": {
            "id": "cb",
            "chat_instance": "ci",
            "from": {"id": user_id, "is_bot": False, "first_name": "Admin"},
            "data": data,
            "message": {
                "message_id": 3,
                "date": 1700000000,
                "chat": {"id": user_id, "type": "private"},
                "text": "confirm?",
            },
        },
    }


async def send(client, text: str, user_id: int = 999):
    await client.post("/tg/webhook", json=command(text, user_id), headers=WEBHOOK)


async def test_stats_for_admins_only(client, db, bot_session):
    await login(client, 1)
    await login(client, 2, start_param="r_1")
    await send(client, "/stats", user_id=1)
    assert bot_session.of_type("SendMessage") == []
    await send(client, "/stats")
    [msg] = bot_session.of_type("SendMessage")
    assert "Игроков: 2" in msg.text
    assert "DAU / WAU / MAU: 2 / 2 / 2" in msg.text
    names = set((await db.execute(select(Event.name))).scalars())
    assert "register" in names


async def test_ban_and_suspects(client, db, bot_session):
    await login(client, 1)
    await db.execute(update(User).where(User.id == 1).values(suspicion=30))
    await db.commit()
    await send(client, "/suspects")
    assert "флагов 30" in bot_session.of_type("SendMessage")[-1].text
    await send(client, "/ban 1")
    assert (await client.post("/api/session", json={}, headers=auth(1))).status_code == 403
    await send(client, "/unban 1")
    assert (await client.post("/api/session", json={}, headers=auth(1))).status_code == 200

    clan = Clan(kind="channel", tg_chat_id=-5, title="x", color="#000000")
    db.add(clan)
    await db.commit()
    await send(client, f"/ban_clan {clan.id}")
    await db.refresh(clan)
    assert clan.banned is True


async def test_broadcast_requires_confirmation(client, db, bot_session):
    from app.bot.handlers.admin import AdminCb

    for uid in (1, 2, 3):
        await login(client, uid)
    await db.execute(update(User).where(User.id == 3).values(notify_enabled=False))
    await db.commit()

    await send(client, "/broadcast Новый сезон стартует!")
    assert await get_redis().llen(QUEUE_KEY) == 0
    await client.post(
        "/tg/webhook", json=callback(AdminCb(action="broadcast").pack()), headers=WEBHOOK
    )
    items = await get_redis().lrange(QUEUE_KEY, 0, -1)
    assert len(items) == 2
    assert "Новый сезон" in items[0]


async def test_season_end_command(client, db, bot_session):
    from app.bot.handlers.admin import AdminCb

    await season_service.ensure_active_season(db, T0)
    await db.commit()
    await send(client, "/season_end")
    await client.post(
        "/tg/webhook", json=callback(AdminCb(action="season_end").pack()), headers=WEBHOOK
    )
    seasons = (await db.execute(select(Season).order_by(Season.number))).scalars().all()
    assert [s.status for s in seasons] == ["finished", "active"]


async def test_combo_set(client, db, bot_session):
    await send(client, "/combo_set today market walls barracks")
    combo = await db.get(DailyCombo, T0.date())
    assert combo.card_ids == ["market", "walls", "barracks"]
    await send(client, "/combo_set today market market walls")
    assert "3 разные" in bot_session.of_type("SendMessage")[-1].text


async def test_gifts(client, bot_session):
    sticker = Sticker(
        file_id="f", file_unique_id="u", type="regular", width=1, height=1,
        is_animated=False, is_video=False, emoji="🧸",
    )  # fmt: skip
    bot_session.responses["GetAvailableGifts"] = Gifts(
        gifts=[Gift(id="gift1", sticker=sticker, star_count=15)]
    )
    await send(client, "/gifts")
    assert "gift1 — 15 ⭐" in bot_session.of_type("SendMessage")[-1].text
    await send(client, "/gift 1 gift1 Победителю сезона")
    [gift] = bot_session.of_type("SendGift")
    assert (gift.user_id, gift.gift_id, gift.text) == (1, "gift1", "Победителю сезона")
