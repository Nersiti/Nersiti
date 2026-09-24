from __future__ import annotations

from datetime import timedelta

import pytest
from aiogram.methods import AnswerInlineQuery, SendMessage, SendPhoto
from sqlalchemy import update

from app import keyboards as kb
from app.db.models import Auction, Card, User
from app.game import service as game_service
from app.game.battle import BattleResult
from app.main import game_tick
from app.utils import utcnow
from tests.conftest import ADMIN_ID, BotHarness
from tests.fake import callback_update, inline_update, message_update


def _button(request: SendMessage, prefix: str) -> str:
    for row in request.reply_markup.inline_keyboard:
        for button in row:
            if button.callback_data and button.callback_data.startswith(prefix):
                return button.callback_data
    raise AssertionError(f"no button {prefix}")


async def claim(h: BotHarness, user_id: int, word: str, name: str | None = None) -> None:
    await h.feed(message_update(word, user_id=user_id, name=name))
    offer = h.session.of(SendMessage)[-1]
    await h.feed(callback_update(_button(offer, "w:"), user_id=user_id))


async def make_players(h: BotHarness) -> None:
    await h.feed(message_update("/start", user_id=100, name="Аня"))
    await h.feed(message_update("/start", user_id=200, name="Боря"))
    await claim(h, 100, "какао", "Аня")
    await claim(h, 200, "понедельник утром", "Боря")
    await claim(h, 200, "вечерний чай", "Боря")  # второе слово: последнее слово игрока захватить нельзя


def fixed_result(attacker_won: bool):  # type: ignore[no-untyped-def]
    def fake(a, d, rng):  # type: ignore[no-untyped-def]
        return BattleResult(attacker_won, 3, (10 if attacker_won else 0, 0 if attacker_won else 10), (a.hp, d.hp))

    return fake


async def unprotect(h: BotHarness, word: str) -> None:
    async with h.ctx.db.begin() as s:
        await s.execute(update(Card).where(Card.word == word).values(protected_until=utcnow() - timedelta(minutes=1)))


async def give(h: BotHarness, user_id: int, crystals: int) -> None:
    async with h.ctx.db.begin() as s:
        await s.execute(update(User).where(User.id == user_id).values(crystals=crystals))


# ---------- слова ----------


async def test_start_gives_crystals(harness: BotHarness) -> None:
    await harness.feed(message_update("/start", user_id=100))
    user = await harness.user(100)
    assert user.crystals == harness.ctx.settings.start_crystals
    welcome = harness.session.of(SendMessage)[0]
    assert "завладеть любым словом" in welcome.text
    assert welcome.reply_markup.keyboard[0][0].text == kb.BTN_CLAIM


async def test_claim_free_word_creates_card(harness: BotHarness) -> None:
    await harness.feed(message_update("/start", user_id=100))
    await harness.feed(message_update("  Бывший!  ", user_id=100))
    assert "никому не принадлежит" in harness.session.of(SendMessage)[-1].text

    await harness.feed(callback_update(_button(harness.session.of(SendMessage)[-1], "w:"), user_id=100))
    card = await harness.card("бывший")
    assert card.status == "active" and card.owner_id == 100 and card.creator_id == 100
    assert card.display == "Бывший" and card.file_id and card.value > 0 and card.has_art
    assert card.protected_until and card.protected_until > utcnow()
    photo = harness.session.of(SendPhoto)[-1]
    assert "«Бывший»" in photo.caption and "Владелец: <b>ты</b>" in photo.caption
    user = await harness.user(100)
    assert user.quills_today == 1 and user.words_created == 1
    assert any("теперь твоё" in t for t in harness.session.texts())


async def test_taken_word_shows_owner_card(harness: BotHarness) -> None:
    await make_players(harness)
    harness.session.clear()
    await harness.feed(message_update("КАКАО", user_id=200))
    photo = harness.session.of(SendPhoto)[-1]
    assert "Владелец: Аня" in photo.caption
    buttons = [b.text for row in photo.reply_markup.inline_keyboard for b in row]
    assert any("Защищено до" in b for b in buttons) and any("выкуп" in b for b in buttons)  # иммунитет нового слова


async def test_reserved_invalid_and_forbidden_words(harness: BotHarness) -> None:
    await harness.feed(message_update("/start", user_id=100))
    for text in ("деньги", "!!!", "раз два три четыре пять", "порно"):
        await harness.feed(message_update(text, user_id=100))
    texts = harness.session.texts()
    assert any("аукционе" in t for t in texts)
    assert sum("не похоже на слово" in t for t in texts) == 2
    assert any("нельзя" in t for t in texts)


async def test_quills_limit_then_paid_quill(harness_factory) -> None:  # type: ignore[no-untyped-def]
    h = await harness_factory(free_quills_per_day=1, start_crystals=0, quill_price=15)
    await h.feed(message_update("/start", user_id=100))
    await claim(h, 100, "кот учёного")
    await h.feed(message_update("пес", user_id=100))
    assert "15 💎" in h.session.of(SendMessage)[-1].text
    await h.feed(callback_update(_button(h.session.of(SendMessage)[-1], "w:"), user_id=100))
    assert any("Нужно 15 💎" in t for t in h.session.texts())

    await give(h, 100, 20)
    await claim(h, 100, "пес")
    assert (await h.card("пес")).owner_id == 100
    assert (await h.user(100)).crystals == 5


async def test_forbidden_by_llm_refunds_quill(harness: BotHarness) -> None:
    class Strict:
        async def complete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            return '{"allowed": false, "reason": "имя реального человека"}'

        async def close(self) -> None:
            return None

    harness.ctx.game.llm = Strict()  # type: ignore[assignment]
    await harness.feed(message_update("/start", user_id=100))
    await claim(harness, 100, "иван петров")
    assert any("имя реального человека" in t for t in harness.session.texts())
    user = await harness.user(100)
    assert user.quills_today == 0
    assert (await harness.ctx.game.lookup("иван петров")).card is None


async def test_llm_creature_is_used(harness: BotHarness) -> None:
    class Smart:
        async def complete(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            return (
                'Вот карта: {"allowed": true, "name": "Кофеин", "title": "Бодрящий", "element": "fire", '
                '"class": "warrior", "atk": 9, "def": 3, "hp": 4, "ability": "Эспрессо", '
                '"ability_text": "Будит всех", "lore": "Из турки", "art": "coffee dragon"}'
            )

        async def close(self) -> None:
            return None

    harness.ctx.game.llm = Smart()  # type: ignore[assignment]
    await harness.feed(message_update("/start", user_id=100))
    await claim(harness, 100, "какао")
    card = await harness.card("какао")
    assert (card.name, card.element, card.klass, card.ability) == ("Кофеин", "fire", "warrior", "Эспрессо")
    assert card.atk > card.def_


async def test_two_players_race_for_word(harness: BotHarness) -> None:
    await harness.feed(message_update("/start", user_id=100))
    await harness.feed(message_update("/start", user_id=200))
    await harness.feed(message_update("сквозняк", user_id=100))
    first = _button(harness.session.of(SendMessage)[-1], "w:")
    await harness.feed(message_update("сквозняк", user_id=200))
    second = _button(harness.session.of(SendMessage)[-1], "w:")
    await harness.feed(callback_update(first, user_id=100))
    await harness.feed(callback_update(second, user_id=200))
    assert (await harness.card("сквозняк")).owner_id == 100
    assert any("быстрее" in t for t in harness.session.texts())
    assert (await harness.user(200)).quills_today == 0


async def test_gpu_offline_card_still_created_and_redraw(harness: BotHarness) -> None:
    class Broken:
        async def generate(self, req):  # type: ignore[no-untyped-def]
            raise RuntimeError("GPU off")

        async def close(self) -> None:
            return None

    real = harness.ctx.game.images
    harness.ctx.game.images = Broken()  # type: ignore[assignment]
    await harness.feed(message_update("/start", user_id=100))
    await claim(harness, 100, "туча")
    card = await harness.card("туча")
    assert card.status == "active" and not card.has_art

    harness.ctx.game.images = real
    await harness.feed(callback_update(kb.CardCb(id=card.id, action="redraw").pack(), user_id=100))
    assert (await harness.card("туча")).has_art
    assert (await harness.user(100)).crystals == harness.ctx.settings.start_crystals  # первая дорисовка бесплатно


# ---------- бои ----------


async def test_friendly_battle(harness: BotHarness, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(game_service, "simulate", fixed_result(True))
    await make_players(harness)
    mine, target = await harness.card("какао"), await harness.card("понедельник утром")
    harness.session.clear()
    await harness.feed(callback_update(kb.FightCb(mine=mine.id, target=target.id, capture=False).pack(), user_id=100))

    assert any("ПОБЕДА" in t for t in harness.session.texts())
    a, b = await harness.user(100), await harness.user(200)
    assert a.battles_today == 1 and a.wins == 1 and a.rating > 1000 and b.rating < 1000 and b.losses == 1
    assert (await harness.card("какао")).xp == 30 and (await harness.card("понедельник утром")).owner_id == 200


async def test_arena_finds_opponent(harness: BotHarness) -> None:
    await make_players(harness)
    mine = await harness.card("какао")
    harness.session.clear()
    await harness.feed(callback_update(kb.ArenaCb(mine=mine.id).pack(), user_id=100))
    assert any("«Понедельник утром»" in t or "«Вечерний чай»" in t for t in harness.session.texts())


async def test_capture_blocked_by_immunity(harness: BotHarness) -> None:
    await make_players(harness)
    mine, target = await harness.card("какао"), await harness.card("понедельник утром")
    await harness.feed(callback_update(kb.FightCb(mine=mine.id, target=target.id, capture=True).pack(), user_id=100))
    assert any("под защитой" in t for t in harness.session.texts())
    assert (await harness.card("понедельник утром")).owner_id == 200


async def test_capture_success(harness: BotHarness, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(game_service, "simulate", fixed_result(True))
    await make_players(harness)
    await unprotect(harness, "понедельник утром")
    target = await harness.card("понедельник утром")
    await give(harness, 100, target.value + 5)
    before_b = (await harness.user(200)).crystals
    mine = await harness.card("какао")
    await harness.feed(callback_update(kb.FightCb(mine=mine.id, target=target.id, capture=True).pack(), user_id=100))

    captured = await harness.card("понедельник утром")
    assert captured.owner_id == 100 and captured.protected_until > utcnow()
    assert (await harness.user(100)).crystals == 5
    payout = target.value - target.value * harness.ctx.settings.fee_percent // 100
    assert (await harness.user(200)).crystals == before_b + payout
    assert any(r.chat_id == 200 and "захватил твоё слово" in r.text for r in harness.session.of(SendMessage))


async def test_capture_failure_pays_defender(harness: BotHarness, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(game_service, "simulate", fixed_result(False))
    await make_players(harness)
    await unprotect(harness, "понедельник утром")
    target = await harness.card("понедельник утром")
    await give(harness, 100, target.value)
    mine = await harness.card("какао")
    await harness.feed(callback_update(kb.FightCb(mine=mine.id, target=target.id, capture=True).pack(), user_id=100))
    assert (await harness.card("понедельник утром")).owner_id == 200
    assert (await harness.user(100)).crystals == 0
    assert any(r.chat_id == 200 and "и проиграл" in r.text for r in harness.session.of(SendMessage))


async def test_capture_without_crystals(harness: BotHarness) -> None:
    await make_players(harness)
    await unprotect(harness, "понедельник утром")
    await give(harness, 100, 0)
    mine, target = await harness.card("какао"), await harness.card("понедельник утром")
    await harness.feed(callback_update(kb.FightCb(mine=mine.id, target=target.id, capture=True).pack(), user_id=100))
    assert (await harness.card("понедельник утром")).owner_id == 200
    assert any("Нужно" in t for t in harness.session.texts())


async def test_shield_blocks_capture(harness: BotHarness) -> None:
    await make_players(harness)
    await unprotect(harness, "понедельник утром")
    target = await harness.card("понедельник утром")
    await give(harness, 200, 1000)
    await harness.feed(callback_update(kb.CardCb(id=target.id, action="shield").pack(), user_id=200))
    shielded = await harness.card("понедельник утром")
    assert shielded.shield_until and shielded.shield_until > utcnow() + timedelta(days=2)
    assert (await harness.user(200)).crystals == 1000 - harness.ctx.game.shield_price(target)

    await give(harness, 100, 1000)
    mine = await harness.card("какао")
    await harness.feed(callback_update(kb.FightCb(mine=mine.id, target=target.id, capture=True).pack(), user_id=100))
    assert (await harness.card("понедельник утром")).owner_id == 200
    assert (await harness.user(100)).crystals == 1000


# ---------- выкуп ----------


async def test_offer_accept(harness: BotHarness) -> None:
    await make_players(harness)
    await give(harness, 100, 200)
    await give(harness, 200, 0)
    target = await harness.card("понедельник утром")
    await harness.feed(callback_update(kb.OfferCb(card=target.id, price=100).pack(), user_id=100))
    assert (await harness.user(100)).crystals == 100  # заморожено

    note = [r for r in harness.session.of(SendMessage) if r.chat_id == 200 and "хочет купить" in r.text][-1]
    await harness.feed(callback_update(_button(note, "or:"), user_id=200))
    assert (await harness.card("понедельник утром")).owner_id == 100
    assert (await harness.user(200)).crystals == 90
    assert any(r.chat_id == 100 and "Сделка" in r.text for r in harness.session.of(SendMessage))


async def test_offer_decline_and_expire(harness: BotHarness) -> None:
    await make_players(harness)
    await give(harness, 100, 300)
    target = await harness.card("понедельник утром")
    await harness.feed(callback_update(kb.OfferCb(card=target.id, price=100).pack(), user_id=100))
    offer_id = int(_button([r for r in harness.session.of(SendMessage) if r.chat_id == 200][-1], "or:").split(":")[1])
    await harness.feed(callback_update(kb.OfferReplyCb(id=offer_id, accept=False).pack(), user_id=200))
    assert (await harness.user(100)).crystals == 300

    await harness.feed(callback_update(kb.OfferCb(card=target.id, price=50).pack(), user_id=100))
    assert (await harness.user(100)).crystals == 250
    harness.ctx.settings.offer_ttl_hours = 0
    expired = await harness.ctx.game.expire_offers()
    assert len(expired) == 1 and (await harness.user(100)).crystals == 300


# ---------- аукцион ----------


async def test_auction_bids_and_award(harness: BotHarness) -> None:
    await harness.feed(message_update("/start", user_id=100))
    await harness.feed(message_update("/start", user_id=200))
    await give(harness, 100, 500)
    await give(harness, 200, 500)
    await harness.feed(message_update("/auction_start любовь 2", user_id=ADMIN_ID))
    auction = await harness.ctx.auctions.current()
    assert auction is not None and auction.word == "любовь"

    await harness.feed(callback_update(kb.BidCb(auction=auction.id, amount=50).pack(), user_id=100))
    await harness.feed(callback_update(kb.BidCb(auction=auction.id, amount=55).pack(), user_id=200))  # мало
    assert any("Минимальная ставка" in t for t in harness.session.texts())
    await harness.feed(message_update("/bid 70", user_id=200))
    assert (await harness.user(100)).crystals == 500  # вернули
    assert (await harness.user(200)).crystals == 430
    assert any(r.chat_id == 100 and "перебили" in r.text for r in harness.session.of(SendMessage))

    async with harness.ctx.db.begin() as s:
        await s.execute(update(Auction).values(ends_at=utcnow() - timedelta(seconds=1)))
    await game_tick(harness.bot, harness.ctx)
    card = await harness.card("любовь")
    assert card.owner_id == 200 and card.rarity in ("legendary", "mythic") and card.file_id
    assert (await harness.ctx.auctions.get(auction.id)).card_id == card.id
    assert any(r.chat_id == 200 and "Победа на аукционе" in r.text for r in harness.session.of(SendMessage))

    await game_tick(harness.bot, harness.ctx)  # повторный тик не создаёт вторую карту
    assert len([p for p in harness.session.of(SendPhoto) if p.chat_id == 200]) == 1


async def test_daily_auction_starts_once(harness_factory) -> None:  # type: ignore[no-untyped-def]
    h = await harness_factory(auction_enabled=True, auction_start_hour=0, auction_end_hour=0)
    first = await h.ctx.auctions.maybe_start_daily()
    assert first is not None and first.status == "active"
    assert await h.ctx.auctions.maybe_start_daily() is None


# ---------- виральность ----------


async def test_inline_mode(harness: BotHarness) -> None:
    await make_players(harness)
    await harness.feed(inline_update("кака", user_id=999))
    answer = harness.session.of(AnswerInlineQuery)[-1]
    assert answer.results[0].photo_file_id and "«Какао»" in answer.results[0].caption

    await harness.feed(inline_update("новое слово", user_id=999))
    answer = harness.session.of(AnswerInlineQuery)[-1]
    assert "никому не принадлежит" in answer.results[-1].title
    async with harness.ctx.db.session() as s:
        assert await s.get(User, 999) is None  # инлайн не создаёт игрока


async def test_card_deep_link_and_group_command(harness: BotHarness) -> None:
    await make_players(harness)
    card = await harness.card("какао")
    harness.session.clear()
    await harness.feed(message_update(f"/start c_{card.id}", user_id=300))
    assert any("«Какао»" in (p.caption or "") for p in harness.session.of(SendPhoto))
    assert (await harness.user(300)).source == "card"

    await harness.feed(message_update("/card какао", user_id=300, chat_type="group"))
    assert any("Владелец: Аня" in (p.caption or "") for p in harness.session.of(SendPhoto))


async def test_referral_reward_after_first_word(harness: BotHarness) -> None:
    s = harness.ctx.settings
    await harness.feed(message_update("/start", user_id=100, name="Аня"))
    await harness.feed(message_update("/start ref_100", user_id=200, name="Боря"))
    assert (await harness.user(200)).crystals == s.start_crystals + s.ref_bonus_invitee
    await claim(harness, 200, "лужа", "Боря")
    assert (await harness.user(100)).crystals == s.start_crystals + s.ref_bonus_inviter
    assert any(r.chat_id == 100 and "Боря" in r.text for r in harness.session.of(SendMessage))


async def test_screens_render(harness: BotHarness) -> None:
    await make_players(harness)
    for text in (kb.BTN_CARDS, kb.BTN_TOP, kb.BTN_PROFILE, kb.BTN_ARENA, kb.BTN_AUCTION, kb.BTN_SHOP, kb.BTN_BONUS,
                 kb.BTN_CLAIM, "/rules", "/terms", "/paysupport"):
        await harness.feed(message_update(text, user_id=100, name="Аня"))
    texts = harness.session.texts()
    for fragment in ("Твои слова: 1", "Топ мира слов", "Профиль", "Арена", "аукциона нет", "Магазин",
                     "Бесплатные кристаллы", "Напиши любое слово", "Правила", "Условия", "@support"):
        assert any(fragment in t for t in texts), fragment


async def test_group_plain_messages_ignored(harness: BotHarness) -> None:
    await harness.feed(message_update("какао", user_id=100, chat_type="group"))
    assert not harness.session.of(SendMessage)


async def test_auction_word_cannot_be_claimed_and_refund(harness: BotHarness) -> None:
    await harness.feed(message_update("/start", user_id=100))
    await harness.feed(message_update("/auction_start закат над морем 2", user_id=ADMIN_ID))
    await harness.feed(message_update("закат над морем", user_id=100))
    assert "аукцион" in harness.session.of(SendMessage)[-1].text.lower()
    with pytest.raises(game_service.GameError):
        await harness.ctx.game.reserve(100, "закат над морем", "Закат над морем")

    auction = await harness.ctx.auctions.current()
    await harness.feed(message_update("/start", user_id=200))
    await give(harness, 200, 100)
    await harness.ctx.auctions.bid(200, auction.id, 60)
    # слово всё-таки занято (например, создано до аукциона) — ставка возвращается победителю
    async with harness.ctx.db.begin() as s:
        s.add(Card(word="закат над морем", display="Закат", status="active", owner_id=100, creator_id=100))
        await s.execute(update(Auction).values(ends_at=utcnow() - timedelta(seconds=1)))
    await game_tick(harness.bot, harness.ctx)
    assert (await harness.user(200)).crystals == 100
    assert (await harness.ctx.auctions.get(auction.id)).status == "refunded"


async def test_double_tap_on_own_word(harness: BotHarness) -> None:
    await harness.feed(message_update("/start", user_id=100))
    await harness.feed(message_update("сугроб", user_id=100))
    button = _button(harness.session.of(SendMessage)[-1], "w:")
    await harness.feed(callback_update(button, user_id=100))
    await harness.feed(callback_update(button, user_id=100))
    assert any("уже твоё" in t for t in harness.session.texts())
    assert (await harness.user(100)).quills_today == 1
