from __future__ import annotations

from datetime import timedelta

import pytest
from aiogram.methods import SendMessage, SetMyCommands, SetMyDescription
from sqlalchemy import text, update

from app import keyboards as kb
from app.db.database import add_missing_columns
from app.db.models import Card, User
from app.game import retention
from app.game import service as game_service
from app.main import startup
from app.services import health
from app.services.health import Breaker, GuardedImages, check_images, check_llm
from app.utils import utcnow
from tests.conftest import ADMIN_ID, BotHarness, make_settings
from tests.fake import callback_update, message_update
from tests.test_game import _button, claim, fixed_result, give, make_players, unprotect


def _to(h: BotHarness, chat_id: int) -> list[str]:
    return [r.text for r in h.session.of(SendMessage) if r.chat_id == chat_id]


# ---------- защита новичков ----------


async def test_last_word_cannot_be_captured(harness: BotHarness) -> None:
    await harness.feed(message_update("/start", user_id=100))
    await harness.feed(message_update("/start", user_id=200))
    await claim(harness, 100, "какао")
    await claim(harness, 200, "единственное")
    await unprotect(harness, "единственное")
    await give(harness, 100, 1000)
    target = await harness.card("единственное")
    harness.session.clear()
    await harness.feed(message_update("единственное", user_id=100))
    buttons = [b.text for row in harness.session.requests[-1].reply_markup.inline_keyboard for b in row]
    assert "🔒 Последнее слово игрока" in buttons

    mine = await harness.card("какао")
    await harness.feed(callback_update(kb.FightCb(mine=mine.id, target=target.id, capture=True).pack(), user_id=100))
    assert (await harness.card("единственное")).owner_id == 200
    assert (await harness.user(100)).crystals == 1000


async def test_first_word_is_at_least_rare(harness_factory) -> None:  # type: ignore[no-untyped-def]
    h = await harness_factory()
    for uid in range(300, 312):
        await h.feed(message_update("/start", user_id=uid))
        await claim(h, uid, f"слово номер {uid}")
        assert (await h.card(f"слово номер {uid}")).rarity != "common"
    assert any("Первое слово — твоё" in t for t in h.session.texts())


async def test_capture_button_checks_crystals_first(harness: BotHarness) -> None:
    await make_players(harness)
    await unprotect(harness, "понедельник утром")
    await give(harness, 100, 0)
    target = await harness.card("понедельник утром")
    harness.session.clear()
    await harness.feed(callback_update(kb.CardCb(id=target.id, action="capture").pack(), user_id=100))
    assert any("Нужно" in t for t in harness.session.texts())
    assert not any("Выбери свою карту" in t for t in harness.session.texts())


# ---------- удержание ----------


async def test_revenge_notice(harness: BotHarness, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(game_service, "simulate", fixed_result(True))
    await make_players(harness)
    await unprotect(harness, "понедельник утром")
    target = await harness.card("понедельник утром")
    await give(harness, 100, 500)
    mine = await harness.card("какао")
    await harness.feed(callback_update(kb.FightCb(mine=mine.id, target=target.id, capture=True).pack(), user_id=100))
    assert (await harness.card("понедельник утром")).revenge_to == 200

    assert await retention.notify_revenge(harness.bot, harness.ctx) == 0  # иммунитет ещё идёт
    await unprotect(harness, "понедельник утром")
    assert await retention.notify_revenge(harness.bot, harness.ctx) == 1
    assert any("Иммунитет слова" in t for t in _to(harness, 200))
    assert (await harness.card("понедельник утром")).revenge_to is None


async def test_lord_expired_notice_once(harness: BotHarness) -> None:
    await harness.feed(message_update("/start", user_id=100))
    async with harness.ctx.db.begin() as s:
        await s.execute(update(User).where(User.id == 100).values(premium_until=utcnow() - timedelta(hours=1)))
    assert await retention.notify_lord_expired(harness.bot, harness.ctx) == 1
    assert await retention.notify_lord_expired(harness.bot, harness.ctx) == 0
    assert any("Статус Лорда закончился" in t for t in _to(harness, 100))


async def test_reminders_for_inactive_players(harness: BotHarness) -> None:
    await make_players(harness)
    async with harness.ctx.db.begin() as s:
        await s.execute(update(User).where(User.id == 100).values(last_seen_at=utcnow() - timedelta(days=5)))
    harness.session.clear()
    assert await retention.send_reminders(harness.bot, harness.ctx) == 1
    assert await retention.send_reminders(harness.bot, harness.ctx) == 0
    reminder = _to(harness, 100)[0]
    assert "Аня" in reminder and "Твоих слов: 1" in reminder


async def test_weekly_tournament(harness: BotHarness, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(game_service, "simulate", fixed_result(True))
    await make_players(harness)
    mine, target = await harness.card("какао"), await harness.card("понедельник утром")
    await harness.feed(callback_update(kb.FightCb(mine=mine.id, target=target.id, capture=False).pack(), user_id=100))
    points = (await harness.user(100)).week_points
    assert points > 0 and (await harness.user(200)).week_points == 0

    assert await retention.run_tournament(harness.bot, harness.ctx) == []  # первый запуск только запоминает неделю
    await harness.ctx.kv.set(retention.TOURNAMENT_WEEK, "2000-W01")
    before = (await harness.user(100)).crystals
    winners = await retention.run_tournament(harness.bot, harness.ctx)
    assert [(w.user_id, w.points, w.prize) for w in winners] == [(100, points, 300)]
    user = await harness.user(100)
    assert user.crystals == before + 300 and user.week_points == 0
    assert any("1-е место" in t for t in _to(harness, 100))
    assert await retention.run_tournament(harness.bot, harness.ctx) == []


async def test_referral_daily_cap(harness_factory) -> None:  # type: ignore[no-untyped-def]
    h = await harness_factory(ref_daily_cap=1)
    s = h.ctx.settings
    await h.feed(message_update("/start", user_id=100))
    for uid in (201, 202):
        await h.feed(message_update("/start ref_100", user_id=uid))
        await claim(h, uid, f"друг {uid}")
    assert (await h.user(100)).crystals == s.start_crystals + s.ref_bonus_inviter


# ---------- модерация ----------


async def test_report_and_admin_delete(harness: BotHarness) -> None:
    await make_players(harness)
    await give(harness, 100, 300)
    target = await harness.card("понедельник утром")
    await harness.feed(callback_update(kb.OfferCb(card=target.id, price=100).pack(), user_id=100))
    await harness.feed(callback_update(kb.CardCb(id=target.id, action="report").pack(), user_id=100))
    await harness.feed(callback_update(kb.CardCb(id=target.id, action="report").pack(), user_id=100))
    reports = [r for r in harness.session.of(SendMessage) if r.chat_id == ADMIN_ID and "Жалоба" in r.text]
    assert len(reports) == 1

    await harness.feed(callback_update(_button(reports[0], "ac:"), user_id=ADMIN_ID))
    assert (await harness.ctx.game.lookup("понедельник утром")).card is None
    assert (await harness.user(100)).crystals == 300  # замороженные на выкуп кристаллы вернулись


async def test_offer_command_with_custom_price(harness: BotHarness) -> None:
    await make_players(harness)
    await give(harness, 100, 1000)
    target = await harness.card("понедельник утром")
    await harness.feed(message_update(f"/offer №{target.id} 777", user_id=100))
    assert (await harness.user(100)).crystals == 223
    assert any("777 💎" in t for t in _to(harness, 200))


async def test_claim_button_survives_restart(harness: BotHarness) -> None:
    await harness.feed(message_update("/start", user_id=100))
    await harness.feed(message_update("короткое", user_id=100))
    button = _button(harness.session.of(SendMessage)[-1], "w:")
    assert button == "w:Короткое"
    harness.ctx.tokens._items.clear()  # как после перезапуска
    await harness.feed(callback_update(button, user_id=100))
    assert (await harness.card("короткое")).owner_id == 100

    long_word = "о" * 32  # 32 кириллические буквы = 64 байта — в callback_data не помещается
    await harness.feed(message_update(long_word, user_id=100))
    long_button = _button(harness.session.of(SendMessage)[-1], "w:")
    assert long_button.startswith("w:~")
    await harness.feed(callback_update(long_button, user_id=100))
    assert (await harness.card(long_word)).owner_id == 100


# ---------- надёжность ----------


async def test_art_breaker_skips_gpu_after_failure(harness: BotHarness) -> None:
    calls = 0

    class Down:
        async def generate(self, req):  # type: ignore[no-untyped-def]
            nonlocal calls
            calls += 1
            raise ConnectionError("PC is off")

        async def close(self) -> None:
            return None

    harness.ctx.game.images = GuardedImages(Down(), Breaker(threshold=1, cooldown=60))
    assert await harness.ctx.game.draw_art("cat", False) is None
    assert await harness.ctx.game.draw_art("cat", False) is None
    assert calls == 1  # второй раз видеокарту не ждём


async def test_health_checks(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    async def fake_get(url: str, headers=None):  # type: ignore[no-untyped-def]
        if url.endswith("/models"):
            return {"data": [{"id": "qwen2.5:7b"}]}
        if url.endswith("/system_stats"):
            return {"devices": [{"name": "NVIDIA GeForce RTX 5060"}]}
        if "CheckpointLoaderSimple" in url:
            return {"CheckpointLoaderSimple": {"input": {"required": {"ckpt_name": [["other.safetensors"]]}}}}
        raise ConnectionError(url)

    monkeypatch.setattr(health, "_get_json", fake_get)
    settings = make_settings(tmp_path, llm_backend="openai", image_backend="comfyui")
    assert (await check_llm(settings)).startswith("🟢")
    images = await check_images(settings)
    assert images.startswith("🟡") and "RTX 5060" in images and "other.safetensors" in images
    assert (await check_llm(make_settings(tmp_path, llm_backend="openai", llm_model="llama3"))).startswith("🟡")
    assert (await check_images(make_settings(tmp_path, image_backend="a1111"))).startswith("🔴")


async def test_full_startup_reports_to_admin(harness: BotHarness) -> None:
    await startup(harness.bot, harness.ctx, configure_bot=True, background=False)
    assert harness.session.of(SetMyCommands) and harness.session.of(SetMyDescription)
    report = _to(harness, ADMIN_ID)[-1]
    assert "запущен" in report and "Нейросеть" in report and "Stars" in report


async def test_auto_migration_adds_columns(harness: BotHarness) -> None:
    async with harness.ctx.db.engine.begin() as conn:
        await conn.execute(text("ALTER TABLE users DROP COLUMN ref_day_count"))
        added = await conn.run_sync(add_missing_columns)
    assert "users.ref_day_count" in added
    await harness.feed(message_update("/start", user_id=100))
    assert (await harness.user(100)).ref_day_count == 0


async def test_group_start(harness: BotHarness) -> None:
    await harness.feed(message_update("/start", user_id=100, chat_type="group"))
    assert "Хозяин Слова" in harness.session.of(SendMessage)[-1].text


async def test_stale_reservation_refunds_paid_quill(harness_factory) -> None:  # type: ignore[no-untyped-def]
    h = await harness_factory(free_quills_per_day=0, quill_price=15)
    await h.feed(message_update("/start", user_id=100))
    card_id, spend = await h.ctx.game.reserve(100, "обрыв связи", "Обрыв связи")
    assert spend.how == "paid" and (await h.user(100)).crystals == h.ctx.settings.start_crystals - 15
    async with h.ctx.db.begin() as s:
        await s.execute(update(Card).where(Card.id == card_id).values(created_at=utcnow() - timedelta(hours=1)))
    await h.ctx.game.cleanup_stale()
    assert (await h.ctx.game.lookup("обрыв связи")).card is None
    assert (await h.user(100)).crystals == h.ctx.settings.start_crystals


async def test_banned_players_hidden_from_top(harness: BotHarness) -> None:
    await make_players(harness)
    await harness.feed(message_update("/ban 200", user_id=ADMIN_ID))
    lords = await harness.ctx.game.top_lords()
    assert [u.id for u, _, _ in lords] == [100]
