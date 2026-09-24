from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from aiogram.methods import CopyMessage, SendMessage
from aiogram.types import Chat, Message

from app import keyboards as kb
from app.game import service as game_service
from tests.conftest import ADMIN_ID, BotHarness
from tests.fake import callback_update, message_update, payment_update
from tests.test_game import claim, fixed_result, make_players


async def test_admin_commands_hidden_from_players(harness: BotHarness) -> None:
    await harness.feed(message_update("/give 100 1000", user_id=100))
    assert (await harness.user(100)).crystals == harness.ctx.settings.start_crystals
    assert any("Не знаю такой команды" in t for t in harness.session.texts())

    await harness.feed(message_update("/give 100 1000", user_id=ADMIN_ID))
    assert (await harness.user(100)).crystals == harness.ctx.settings.start_crystals + 1000
    harness.session.clear()
    await harness.feed(message_update("/stats", user_id=ADMIN_ID))
    assert "Игроков: <b>2</b>" in harness.session.texts()[0]


async def test_premium_and_user_card(harness: BotHarness) -> None:
    await make_players(harness)
    await harness.feed(message_update("/premium 100 7", user_id=ADMIN_ID))
    assert (await harness.user(100)).premium_until is not None
    harness.session.clear()
    await harness.feed(message_update("/user 100", user_id=ADMIN_ID))
    assert "Слов: 1" in harness.session.texts()[-1]


async def test_delcard_frees_word(harness: BotHarness) -> None:
    await make_players(harness)
    await harness.feed(message_update("/delcard какао", user_id=ADMIN_ID))
    assert (await harness.ctx.game.lookup("какао")).card is None
    await claim(harness, 200, "какао")
    assert (await harness.card("какао")).owner_id == 200


async def test_promo_codes(harness: BotHarness) -> None:
    await harness.feed(message_update("/promo_new BLOG50 50 1", user_id=ADMIN_ID))
    await harness.feed(message_update("/start", user_id=100))
    await harness.feed(message_update("/promo blog50", user_id=100))
    await harness.feed(message_update("/promo BLOG50", user_id=100))
    await harness.feed(message_update("/start", user_id=200))
    await harness.feed(message_update("/promo BLOG50", user_id=200))

    base = harness.ctx.settings.start_crystals
    assert (await harness.user(100)).crystals == base + 50
    assert (await harness.user(200)).crystals == base
    texts = harness.session.texts()
    assert any("уже активировал" in t for t in texts) and any("закончился" in t for t in texts)


async def test_daily_bonus_once(harness: BotHarness) -> None:
    await harness.feed(message_update("/start", user_id=100))
    daily = kb.MenuCb(action="daily").pack()
    await harness.feed(callback_update(daily, user_id=100))
    await harness.feed(callback_update(daily, user_id=100))
    s = harness.ctx.settings
    assert (await harness.user(100)).crystals == s.start_crystals + s.daily_bonus


async def test_broadcast(harness: BotHarness) -> None:
    for uid in (ADMIN_ID, 100, 200, 300):
        await harness.feed(message_update("/start", user_id=uid))
    await harness.feed(message_update("/ban 300", user_id=ADMIN_ID))
    source = Message(message_id=555, date=datetime.now(UTC), chat=Chat(id=ADMIN_ID, type="private"), text="Новость!")
    await harness.feed(message_update("/broadcast", user_id=ADMIN_ID, reply_to_message=source))
    assert "3 пользователям" in harness.session.texts()[-1]

    await harness.feed(callback_update(kb.BroadcastCb(action="go").pack(), user_id=ADMIN_ID))
    await asyncio.gather(*harness.ctx.tasks)
    assert sorted(c.chat_id for c in harness.session.of(CopyMessage)) == [ADMIN_ID, 100, 200]
    assert "Доставлено: 3" in harness.session.of(SendMessage)[-1].text


async def test_sources_and_links(harness: BotHarness) -> None:
    await harness.feed(message_update("/start src_vk", user_id=100))
    await harness.feed(message_update("/start src_vk", user_id=200))
    await harness.feed(message_update("/start", user_id=300))
    await harness.feed(payment_update("cr100:100", "XTR", 50, "c1", user_id=100))
    harness.session.clear()
    await harness.feed(message_update("/sources", user_id=ADMIN_ID))
    report = harness.session.texts()[-1]
    assert "<code>vk</code>: 2 / 1 (50.0%) / 50 ⭐ / 0 ₽" in report and "<code>organic</code>: 2 / 0" in report

    await harness.feed(message_update("/link tiktok_1", user_id=ADMIN_ID))
    assert "https://t.me/test_bot?start=src_tiktok_1" in harness.session.texts()[-1]


async def test_ad_after_battles(harness_factory, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(game_service, "simulate", fixed_result(True))
    h = await harness_factory(ad_every=2)
    await h.feed(message_update("/setad Лучший канал: <b>@words_news</b>", user_id=ADMIN_ID))
    await make_players(h)
    mine, target = await h.card("какао"), await h.card("понедельник утром")
    h.session.clear()
    fight = kb.FightCb(mine=mine.id, target=target.id, capture=False).pack()
    await h.feed(callback_update(fight, user_id=100))
    await h.feed(callback_update(fight, user_id=100))
    ads = [t for t in h.session.texts() if "Реклама" in t]
    assert len(ads) == 1 and "@words_news" in ads[0]


async def test_required_channel_gate(harness_factory) -> None:  # type: ignore[no-untyped-def]
    h = await harness_factory(required_channels="@news_channel")
    await h.feed(message_update("/start", user_id=100))
    h.session.member_status = "left"
    await claim(h, 100, "ливень")
    assert any("подпишись" in t for t in h.session.texts())
    assert (await h.ctx.game.lookup("ливень")).card is None

    h.session.member_status = "member"
    await h.feed(callback_update(kb.MenuCb(action="check_sub").pack(), user_id=100))
    await claim(h, 100, "ливень")
    assert (await h.card("ливень")).owner_id == 100
