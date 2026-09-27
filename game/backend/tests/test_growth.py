"""Stage 10: referrals, tasks, rewarded ads, self-serve advertising."""

from datetime import UTC, datetime, timedelta

import h3
import pytest
from aiogram.types import Chat
from sqlalchemy import select, update

from app.config import get_settings
from app.game import player_service
from app.models import AdView, Clan, Referral, Task, User
from tests.helpers import auth, login, seed_world
from tests.test_clans import member

T0 = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
WEBHOOK = {"X-Telegram-Bot-Api-Secret-Token": "test-secret"}
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


async def reload(db, model, pk):
    obj = await db.get(model, pk)
    await db.refresh(obj)
    return obj


# --- Referrals -----------------------------------------------------------------------


async def test_referral_bonuses(client, db, clock):
    await login(client, 1)
    await login(client, 2, start_param="r_1")
    await login(client, 3, start_param="r_1", is_premium=True)
    assert (await reload(db, User, 2)).coins == 1000 + 5000
    assert (await reload(db, User, 1)).coins == 1000 + 5000 + 25000
    assert (await db.get(Referral, 2)).inviter_id == 1

    # Level 3 bonus is paid once.
    await db.execute(update(User).where(User.id == 2).values(total_earned=25_000))
    await db.commit()
    await login(client, 2)
    await login(client, 2)
    assert (await reload(db, User, 1)).coins == 1000 + 5000 + 25000 + 25000


async def test_mentor_bonus_claim(client, db, clock):
    await login(client, 1)
    await login(client, 2, start_param="r_1")
    await db.execute(update(User).where(User.id == 2).values(passive_earned_total=10_000))
    await db.commit()

    summary = (await client.get("/api/referrals", headers=auth(1))).json()
    assert summary["count"] == 1
    assert summary["pending_bonus"] == 500
    assert summary["link"] == "https://t.me/test_bot?startapp=r_1"

    res = await client.post("/api/referrals/claim", headers=auth(1))
    assert res.json()["reward"] == 500
    assert (await client.post("/api/referrals/claim", headers=auth(1))).status_code == 429
    clock.now += timedelta(hours=1, seconds=1)
    assert (await client.post("/api/referrals/claim", headers=auth(1))).json()["reward"] == 0


async def test_invitee_joins_inviter_channel_clan(client, db, clock):
    ids = await seed_world(db)
    await login(client, 1)
    await client.post(
        "/api/onboarding", json={"country_code": "RU", "city_id": ids["kazan"]}, headers=auth(1)
    )
    clan = Clan(kind="channel", tg_chat_id=-7, title="Канал", color="#000000")
    db.add(clan)
    await db.commit()
    await db.execute(update(User).where(User.id == 1).values(clan_id=clan.id))
    await db.commit()

    await login(client, 2, start_param="r_1")
    res = await client.post(
        "/api/onboarding", json={"country_code": "RU", "city_id": ids["moscow"]}, headers=auth(2)
    )
    assert res.json()["state"]["clan"]["id"] == clan.id


# --- Tasks ---------------------------------------------------------------------------


async def test_channel_task_verified_and_capped(client, db, clock, bot_session):
    await login(client, 1)
    await login(client, 2)
    task = Task(
        kind="channel_sub", title_ru="Подпишись", title_en="Subscribe", url="https://t.me/x",
        tg_chat_id=-100, reward=5000, status="active", max_completions=1, completions=0,
    )  # fmt: skip
    db.add(task)
    await db.commit()

    tasks = (await client.get("/api/tasks", headers=auth(1))).json()["tasks"]
    assert tasks == [
        {"id": task.id, "kind": "channel_sub", "title": "Подпишись", "url": "https://t.me/x",
         "reward": 5000, "completed": False}
    ]  # fmt: skip

    bot_session.responses["GetChatMember"] = lambda m: member(m.user_id, "left")
    res = await client.post(f"/api/tasks/{task.id}/check", headers=auth(1))
    assert res.json()["detail"] == "not_subscribed"

    from app.redis_client import get_redis

    await get_redis().delete("sub:-100:1")
    bot_session.responses["GetChatMember"] = lambda m: member(m.user_id, "member")
    res = await client.post(f"/api/tasks/{task.id}/check", headers=auth(1))
    assert res.json()["reward"] == 5000
    assert (await client.post(f"/api/tasks/{task.id}/check", headers=auth(1))).status_code == 409
    # The only slot is taken: the task is finished for everyone else.
    assert (await client.post(f"/api/tasks/{task.id}/check", headers=auth(2))).status_code == 404
    assert (await reload(db, Task, task.id)).status == "done"


async def test_link_task_pays_on_check(client, db, clock):
    await login(client, 1)
    task = Task(kind="link", title_ru="Сайт", title_en="Site", url="https://example.com",
                reward=700, status="active", completions=0)  # fmt: skip
    db.add(task)
    await db.commit()
    res = await client.post(f"/api/tasks/{task.id}/check", headers=auth(1))
    assert res.json()["reward"] == 700


# --- Ads -----------------------------------------------------------------------------


@pytest.fixture
def ads_on(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "adsgram_block_id", "1234")
    monkeypatch.setattr(settings, "ads_callback_secret", "s3cret")


async def test_ads_disabled_without_block_id(client, clock):
    await login(client, 1)
    res = await client.post("/api/ads/intent", json={"reward_type": "energy"}, headers=auth(1))
    assert res.json()["detail"] == "ads_disabled"


async def test_ad_reward_only_via_callback(client, db, clock, ads_on):
    await login(client, 1)
    await db.execute(update(User).where(User.id == 1).values(energy=0, energy_updated_at=T0))
    await db.commit()
    res = await client.post("/api/ads/intent", json={"reward_type": "energy"}, headers=auth(1))
    assert res.json() == {"block_id": "1234"}

    assert (await client.get("/api/ads/callback?userid=1&secret=wrong")).status_code == 403
    res = await client.get("/api/ads/callback?userid=1&secret=s3cret")
    assert res.json() == {"ok": True, "reward": "energy"}
    assert (await reload(db, User, 1)).energy == 1000
    assert len((await db.execute(select(AdView))).scalars().all()) == 1


async def test_ad_daily_limit_and_attack_boost(client, db, clock, ads_on):
    ids = await seed_world(db)
    await login(client, 1)
    await client.post(
        "/api/onboarding", json={"country_code": "RU", "city_id": ids["kazan"]}, headers=auth(1)
    )
    await db.execute(update(User).where(User.id == 1).values(coins=100_000))
    await db.commit()

    await client.post("/api/ads/intent", json={"reward_type": "attack"}, headers=auth(1))
    assert (await client.get("/api/ads/callback?userid=1&secret=s3cret")).json()[
        "reward"
    ] == "attack"
    res = await client.post(
        f"/api/sector/{KAZAN_CENTER}/action", json={"amount": 1000}, headers=auth(1)
    )
    assert res.json()["result"]["power"] == 1500  # ×1.5 once

    for _ in range(9):
        await client.get("/api/ads/callback?userid=1&secret=s3cret")
    assert (await client.get("/api/ads/callback?userid=1&secret=s3cret")).json()["ok"] is False
    res = await client.post("/api/ads/intent", json={"reward_type": "energy"}, headers=auth(1))
    assert res.json()["detail"] == "daily_limit"


# --- Self-serve advertising (/promote) -----------------------------------------------


def private(user_id: int, **extra) -> dict:
    return {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "date": 1700000000,
            "chat": {"id": user_id, "type": "private"},
            "from": {"id": user_id, "is_bot": False, "first_name": "Adv", "language_code": "ru"},
            **extra,
        },
    }


def callback(user_id: int, data: str) -> dict:
    return {
        "update_id": 2,
        "callback_query": {
            "id": "cb",
            "chat_instance": "ci",
            "from": {"id": user_id, "is_bot": False, "first_name": "Adv", "language_code": "ru"},
            "data": data,
        },
    }


async def test_promote_full_flow(client, db, clock, bot_session):
    from app.bot.handlers.promote import PromoCb

    await client.post(
        "/tg/webhook",
        json=private(
            5, text="/promote", entities=[{"type": "bot_command", "offset": 0, "length": 8}]
        ),
        headers=WEBHOOK,
    )
    prompt = bot_session.of_type("SendMessage")[-1]
    assert prompt.reply_markup.keyboard[0][0].request_chat.request_id == 3

    bot_session.responses["GetChatMember"] = lambda m: member(m.user_id, "administrator")
    await client.post(
        "/tg/webhook",
        json=private(
            5,
            chat_shared={"request_id": 3, "chat_id": -300, "title": "Новости", "username": "news"},
        ),
        headers=WEBHOOK,
    )
    packages = bot_session.of_type("SendMessage")[-1]
    assert len(packages.reply_markup.inline_keyboard) == 3

    await client.post(
        "/tg/webhook", json=callback(5, PromoCb(action="pkg", value=2).pack()), headers=WEBHOOK
    )
    [invoice] = bot_session.of_type("SendInvoice")
    assert invoice.payload == "promo|5|-300:2"
    assert invoice.prices[0].amount == 1000

    pre = {
        "update_id": 3,
        "pre_checkout_query": {
            "id": "q", "from": {"id": 5, "is_bot": False, "first_name": "Adv"},
            "currency": "XTR", "total_amount": 1000, "invoice_payload": "promo|5|-300:2",
        },
    }  # fmt: skip
    await client.post("/tg/webhook", json=pre, headers=WEBHOOK)
    assert bot_session.of_type("AnswerPreCheckoutQuery")[-1].ok is True

    paid = private(
        5,
        successful_payment={
            "currency": "XTR", "total_amount": 1000, "invoice_payload": "promo|5|-300:2",
            "telegram_payment_charge_id": "promo-1", "provider_payment_charge_id": "",
        },
    )  # fmt: skip
    await client.post("/tg/webhook", json=paid, headers=WEBHOOK)
    await client.post("/tg/webhook", json=paid, headers=WEBHOOK)  # re-delivery
    tasks = (await db.execute(select(Task))).scalars().all()
    assert len(tasks) == 1
    task = tasks[0]
    assert (task.status, task.max_completions, task.url) == ("pending", 1000, "https://t.me/news")
    admin_msg = [m for m in bot_session.of_type("SendMessage") if m.chat_id == 999]
    assert admin_msg and "Новости" in admin_msg[0].text

    # Non-admins cannot moderate; the admin approves.
    await client.post(
        "/tg/webhook",
        json=callback(5, PromoCb(action="approve", value=task.id).pack()),
        headers=WEBHOOK,
    )
    assert (await reload(db, Task, task.id)).status == "pending"
    await client.post(
        "/tg/webhook",
        json=callback(999, PromoCb(action="approve", value=task.id).pack()),
        headers=WEBHOOK,
    )
    assert (await reload(db, Task, task.id)).status == "active"


async def test_promote_rejection_refunds(client, db, clock, bot_session):
    from app.bot.handlers.promote import PromoCb

    task = Task(
        kind="channel_sub", title_ru="x", title_en="x", url="u", tg_chat_id=-1, reward=5000,
        status="pending", max_completions=100, completions=0, sponsor_user_id=5, stars_paid=150,
        payment_charge_id="promo-9",
    )  # fmt: skip
    db.add(task)
    await db.commit()
    await client.post(
        "/tg/webhook",
        json=callback(999, PromoCb(action="reject", value=task.id).pack()),
        headers=WEBHOOK,
    )
    [refund] = bot_session.of_type("RefundStarPayment")
    assert (refund.user_id, refund.telegram_payment_charge_id) == (5, "promo-9")
    assert (await reload(db, Task, task.id)).status == "rejected"


async def test_admin_task_add(client, db, bot_session):
    bot_session.responses["GetChat"] = Chat(id=-555, type="channel", title="Канал", username="chan")
    bot_session.responses["GetChatMember"] = lambda m: member(m.user_id, "administrator")
    text = "/task_add @chan 3000 50 Подпишись на канал"
    await client.post(
        "/tg/webhook",
        json=private(999, text=text, entities=[{"type": "bot_command", "offset": 0, "length": 9}]),
        headers=WEBHOOK,
    )
    task = (await db.execute(select(Task))).scalar_one()
    assert (task.tg_chat_id, task.reward, task.max_completions, task.url) == (
        -555,
        3000,
        50,
        "https://t.me/chan",
    )
    assert task.title_ru == "Подпишись на канал"
