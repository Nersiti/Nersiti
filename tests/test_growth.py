from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from aiogram.methods import AnswerPreCheckoutQuery, CopyMessage, SendMessage, SendPhoto
from aiogram.types import Chat, Message

from app import keyboards as kb
from app.services.growth import load_showcase_items, post_showcase
from app.services.images import STYLES
from tests.conftest import ADMIN_ID, BotHarness
from tests.fake import callback_update, message_update, payment_update, pre_checkout_update


async def test_broadcast_to_all_users(harness: BotHarness) -> None:
    for uid in (ADMIN_ID, 100, 200, 300):
        await harness.feed(message_update("/start", user_id=uid))
    await harness.feed(message_update("/ban 300", user_id=ADMIN_ID))

    source = Message(
        message_id=555, date=datetime.now(UTC), chat=Chat(id=ADMIN_ID, type="private"), text="Новость!"
    )
    await harness.feed(message_update("/broadcast", user_id=ADMIN_ID, reply_to_message=source))
    assert "3 пользователям" in harness.session.texts()[-1]

    await harness.feed(callback_update(kb.BroadcastCb(action="go").pack(), user_id=ADMIN_ID))
    await asyncio.gather(*harness.ctx.tasks)
    copies = harness.session.of(CopyMessage)
    assert sorted(c.chat_id for c in copies) == [ADMIN_ID, 100, 200]
    assert all(c.message_id == 555 for c in copies)
    assert "Доставлено: 3" in harness.session.of(SendMessage)[-1].text


async def test_banned_user_is_ignored_but_payment_recorded(harness: BotHarness) -> None:
    await harness.feed(message_update("/start", user_id=100))
    await harness.feed(message_update("/ban 100", user_id=ADMIN_ID))
    harness.session.clear()
    await harness.feed(message_update("привет", user_id=100))
    assert not harness.session.of(SendMessage)

    await harness.feed(pre_checkout_update("c50:100", "XTR", 50))
    assert harness.session.of(AnswerPreCheckoutQuery)[0].ok is False
    await harness.feed(payment_update("c50:100", "XTR", 50, "late-charge"))
    assert (await harness.user(100)).stars_spent == 50


async def test_showcase_post(harness_factory) -> None:  # type: ignore[no-untyped-def]
    h = await harness_factory(showcase_channel="@my_showcase")
    assert await post_showcase(h.bot, h.ctx)
    photo = h.session.of(SendPhoto)[0]
    assert photo.chat_id == "@my_showcase"
    assert photo.reply_markup.inline_keyboard[0][0].url == "https://t.me/test_bot?start=src_showcase"


def test_showcase_prompts_file_is_valid() -> None:
    items = load_showcase_items("promo/showcase_prompts.txt")
    assert len(items) >= 20
    assert all(item.style in STYLES for item in items)


async def test_ad_shown_to_free_users(harness_factory) -> None:  # type: ignore[no-untyped-def]
    h = await harness_factory(ad_every=2)
    await h.feed(message_update("/setad Лучший канал про ИИ: <b>@ai_news</b>", user_id=ADMIN_ID))
    await h.feed(message_update("/start", user_id=100))
    h.session.clear()
    await h.feed(message_update("вопрос 1", user_id=100))
    await h.feed(message_update("вопрос 2", user_id=100))
    ads = [t for t in h.session.texts() if "Реклама" in t]
    assert len(ads) == 1 and "@ai_news" in ads[0]


async def test_sources_report(harness: BotHarness) -> None:
    await harness.feed(message_update("/start src_vk", user_id=100))
    await harness.feed(message_update("/start src_vk", user_id=200))
    await harness.feed(message_update("/start", user_id=300))
    await harness.feed(payment_update("c50:100", "XTR", 50, "c1", user_id=100))
    harness.session.clear()
    await harness.feed(message_update("/sources", user_id=ADMIN_ID))
    report = harness.session.texts()[-1]
    assert "<code>vk</code>: 2 / 1 (50.0%) / 50 ⭐ / 0 ₽" in report
    assert "<code>organic</code>: 2 / 0" in report

    await harness.feed(message_update("/link tiktok_1", user_id=ADMIN_ID))
    assert "https://t.me/test_bot?start=src_tiktok_1" in harness.session.texts()[-1]
