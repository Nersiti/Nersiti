from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import GetChatMember, SendMessage, SendMessageDraft, SendPhoto
from sqlalchemy import func, select

from app import keyboards as kb
from app.db.models import ChatMessage, Usage
from tests.conftest import ADMIN_ID, BotHarness
from tests.fake import callback_update, message_update


async def test_start_creates_user_with_bonus(harness: BotHarness) -> None:
    await harness.feed(message_update("/start", user_id=100))
    user = await harness.user(100)
    assert user.credits == harness.ctx.settings.start_bonus
    assert user.mode == "chat"
    welcome = harness.session.of(SendMessage)[0]
    assert "Привет, Иван" in welcome.text
    assert welcome.reply_markup.keyboard[0][0].text == kb.BTN_CHAT


async def test_source_tag_is_saved_only_for_new_users(harness: BotHarness) -> None:
    await harness.feed(message_update("/start src_vk_post1", user_id=100))
    await harness.feed(message_update("/start src_other", user_id=100))
    assert (await harness.user(100)).source == "vk_post1"


async def test_chat_answer_saves_history_and_usage(harness: BotHarness) -> None:
    await harness.feed(message_update("/start", user_id=100))
    harness.session.clear()
    await harness.feed(message_update("Привет, как дела?", user_id=100))

    assert any("Эхо: Привет, как дела?" in t for t in harness.session.texts())
    user = await harness.user(100)
    assert user.chat_today == 1 and user.total_chat == 1
    async with harness.ctx.db.session() as s:
        assert await s.scalar(select(func.count()).select_from(ChatMessage)) == 2
        assert await s.scalar(select(func.count()).select_from(Usage)) == 1

    await harness.feed(message_update("/new", user_id=100))
    async with harness.ctx.db.session() as s:
        assert await s.scalar(select(func.count()).select_from(ChatMessage)) == 0


async def test_free_limit_then_credits_then_paywall(harness_factory) -> None:  # type: ignore[no-untyped-def]
    h = await harness_factory(free_chat_per_day=2, start_bonus=1, chat_cost=1)
    await h.feed(message_update("/start", user_id=100))
    for i in range(3):
        await h.feed(message_update(f"вопрос {i}", user_id=100))
    user = await h.user(100)
    assert user.chat_today == 2 and user.credits == 0 and user.total_chat == 3

    h.session.clear()
    await h.feed(message_update("ещё вопрос", user_id=100))
    assert any("закончились" in t for t in h.session.texts())
    assert (await h.user(100)).total_chat == 3


async def test_image_generation_and_regenerate(harness: BotHarness) -> None:
    await harness.feed(message_update("/start", user_id=100))
    harness.session.clear()
    await harness.feed(message_update("/img кот-астронавт на Луне", user_id=100))

    photos = harness.session.of(SendPhoto)
    assert len(photos) == 1
    assert "кот-астронавт" in photos[0].caption and "@test_bot" in photos[0].caption
    user = await harness.user(100)
    assert user.images_today == 1 and user.total_images == 1

    regen = photos[0].reply_markup.inline_keyboard[0][0].callback_data
    await harness.feed(callback_update(regen, user_id=100))
    assert len(harness.session.of(SendPhoto)) == 2


async def test_image_mode_uses_plain_text(harness: BotHarness) -> None:
    await harness.feed(message_update("/start", user_id=100))
    await harness.feed(message_update(kb.BTN_IMAGE, user_id=100))
    harness.session.clear()
    await harness.feed(message_update("закат над морем", user_id=100))
    assert len(harness.session.of(SendPhoto)) == 1


async def test_forbidden_prompt_is_not_charged(harness: BotHarness) -> None:
    await harness.feed(message_update("/start", user_id=100))
    await harness.feed(message_update("/img голая девушка", user_id=100))
    assert not harness.session.of(SendPhoto)
    assert (await harness.user(100)).images_today == 0


async def test_referral_bonus_paid_after_first_request(harness: BotHarness) -> None:
    s = harness.ctx.settings
    await harness.feed(message_update("/start", user_id=100, name="Аня"))
    await harness.feed(message_update("/start ref_100", user_id=200, name="Боря"))

    friend = await harness.user(200)
    assert friend.referrer_id == 100 and friend.source == "ref"
    assert friend.credits == s.start_bonus + s.ref_bonus_invitee
    assert (await harness.user(100)).credits == s.start_bonus

    await harness.feed(message_update("первый вопрос", user_id=200, name="Боря"))
    await harness.feed(message_update("второй вопрос", user_id=200, name="Боря"))
    inviter = await harness.user(100)
    assert inviter.credits == s.start_bonus + s.ref_bonus_inviter
    assert inviter.ref_earned == s.ref_bonus_inviter
    assert any(r.chat_id == 100 and "Боря" in r.text for r in harness.session.of(SendMessage))


async def test_self_referral_ignored(harness: BotHarness) -> None:
    await harness.feed(message_update("/start ref_100", user_id=100))
    user = await harness.user(100)
    assert user.referrer_id is None and user.credits == harness.ctx.settings.start_bonus


async def test_daily_bonus_once_per_day(harness: BotHarness) -> None:
    await harness.feed(message_update("/start", user_id=100))
    daily = kb.MenuCb(action="daily").pack()
    await harness.feed(callback_update(daily, user_id=100))
    await harness.feed(callback_update(daily, user_id=100))
    s = harness.ctx.settings
    assert (await harness.user(100)).credits == s.start_bonus + s.daily_bonus


async def test_promo_codes(harness: BotHarness) -> None:
    await harness.feed(message_update("/promo_new BLOG50 50 1", user_id=ADMIN_ID))
    await harness.feed(message_update("/start", user_id=100))
    await harness.feed(message_update("/promo blog50", user_id=100))
    await harness.feed(message_update("/promo BLOG50", user_id=100))
    await harness.feed(message_update("/start", user_id=200))
    await harness.feed(message_update("/promo BLOG50", user_id=200))

    base = harness.ctx.settings.start_bonus
    assert (await harness.user(100)).credits == base + 50
    assert (await harness.user(200)).credits == base
    texts = harness.session.texts()
    assert any("уже активировал" in t for t in texts)
    assert any("закончился" in t for t in texts)


async def test_admin_commands_hidden_from_users(harness: BotHarness) -> None:
    await harness.feed(message_update("/give 100 1000", user_id=100))
    assert (await harness.user(100)).credits == harness.ctx.settings.start_bonus
    assert any("Не знаю такой команды" in t for t in harness.session.texts())

    await harness.feed(message_update("/give 100 1000", user_id=ADMIN_ID))
    assert (await harness.user(100)).credits == harness.ctx.settings.start_bonus + 1000

    harness.session.clear()
    await harness.feed(message_update("/stats", user_id=ADMIN_ID))
    assert "Пользователей: <b>2</b>" in harness.session.texts()[0]


async def test_group_messages_are_ignored(harness: BotHarness) -> None:
    await harness.feed(message_update("привет", user_id=100, chat_type="group"))
    assert not harness.session.of(SendMessage)


async def test_required_channel_gate(harness_factory) -> None:  # type: ignore[no-untyped-def]
    h = await harness_factory(required_channels="@news_channel")
    await h.feed(message_update("/start", user_id=100))
    h.session.member_status = "left"
    await h.feed(message_update("вопрос", user_id=100))
    assert any("подпишись" in t for t in h.session.texts())
    assert (await h.user(100)).chat_today == 0
    assert h.session.of(GetChatMember)[0].chat_id == "@news_channel"

    h.session.member_status = "member"
    await h.feed(callback_update(kb.MenuCb(action="check_sub").pack(), user_id=100))
    await h.feed(message_update("вопрос", user_id=100))
    assert (await h.user(100)).chat_today == 1


async def test_streaming_drafts_with_fallback(harness_factory) -> None:  # type: ignore[no-untyped-def]
    h = await harness_factory(llm_stream=True)
    await h.feed(message_update("/start", user_id=100))
    h.session.errors[SendMessageDraft] = TelegramBadRequest(method=None, message="method not available")  # type: ignore[arg-type]
    await h.feed(message_update("расскажи " + "очень " * 10 + "длинную историю", user_id=100))
    assert any("Эхо: расскажи" in t for t in h.session.texts())


async def test_llm_failure_refunds(harness: BotHarness) -> None:
    class Broken:
        async def complete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("boom")

        async def close(self) -> None:
            return None

    harness.ctx.llm = Broken()  # type: ignore[assignment]
    await harness.feed(message_update("/start", user_id=100))
    await harness.feed(message_update("вопрос", user_id=100))
    user = await harness.user(100)
    assert user.chat_today == 0 and user.total_chat == 0
    assert any("перегружена" in t for t in harness.session.texts())


async def test_all_screens_render(harness: BotHarness) -> None:
    await harness.feed(message_update("/start", user_id=100))
    for text in (kb.BTN_PROFILE, kb.BTN_BUY, kb.BTN_BONUS, kb.BTN_SETTINGS, kb.BTN_CHAT, "/help", "/terms", "/paysupport"):
        await harness.feed(message_update(text, user_id=100))
    for action in ("style", "ratio", "help", "buy", "bonus", "new"):
        await harness.feed(callback_update(kb.MenuCb(action=action).pack(), user_id=100))
    await harness.feed(callback_update(kb.StyleCb(code="anime").pack(), user_id=100))
    await harness.feed(callback_update(kb.RatioCb(code="9x16").pack(), user_id=100))

    user = await harness.user(100)
    assert (user.image_style, user.image_ratio, user.mode) == ("anime", "9x16", "image")
    texts = harness.session.texts()
    for fragment in ("Профиль", "Premium и кредиты", "Бесплатные кредиты", "ref_100", "Настройки", "Условия", "@support"):
        assert any(fragment in t for t in texts), fragment
