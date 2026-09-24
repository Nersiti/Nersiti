"""Main gameplay: words, cards, battles, arena, buyouts, auction, and leaderboards."""

from __future__ import annotations

import logging
import math

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from aiogram.utils.chat_action import ChatActionSender

from app import keyboards as kb
from app import texts
from app.context import Services
from app.db import repo
from app.db.models import Card, User
from app.game.auction import min_next_bid
from app.game.service import REDRAW_PRICE, GameError, is_lord, public_name
from app.game.words import display_form, normalize
from app.services.growth import announce, notify, reward_inviter
from app.services.kv import AD_TEXT
from app.services.moderation import is_prompt_allowed

log = logging.getLogger(__name__)
router = Router(name="game")


# ---------- вспомогательное ----------


async def _owner(ctx: Services, card: Card) -> User | None:
    async with ctx.db.session() as s:
        return await repo.get_user(s, card.owner_id)


async def send_card(bot: Bot, chat_id: int, card: Card, viewer_id: int, ctx: Services) -> None:
    caption = texts.card_caption(card, await _owner(ctx, card), ctx.settings, viewer_id)
    markup = kb.card_kb(card, viewer_id, ctx.game.shield_price(card), REDRAW_PRICE)
    if card.file_id:
        try:
            await bot.send_photo(chat_id, card.file_id, caption=caption, reply_markup=markup)
            return
        except TelegramAPIError as e:
            log.warning("Card %s photo failed: %s", card.id, e)
    await bot.send_message(chat_id, caption, reply_markup=markup)


async def send_error(bot: Bot, chat_id: int, err: GameError, ctx: Services) -> None:
    markup = kb.no_crystals_kb() if err.code == "no_crystals" else None
    await bot.send_message(chat_id, texts.error_text(err, ctx.settings), reply_markup=markup)


async def _gate(bot: Bot, chat_id: int, user: User, ctx: Services) -> bool:
    """Mandatory channel subscription (if enabled) — not required for Lords and admins."""
    if is_lord(user) or ctx.settings.is_admin(user.id):
        return True
    missing = await ctx.gate.missing(bot, user.id)
    if missing:
        await bot.send_message(chat_id, texts.SUBSCRIBE_REQUIRED, reply_markup=kb.channels_kb(missing))
        return False
    return True


async def _store_photo(ctx: Services, card_id: int, message: Message) -> None:
    if message.photo:
        await ctx.game.set_file_id(card_id, message.photo[-1].file_id)


# ---------- меню ----------


@router.message(Command("rules", "help"))
async def cmd_rules(message: Message, ctx: Services) -> None:
    await message.answer(texts.rules_text(ctx.settings))


@router.message(F.text == kb.BTN_CLAIM)
async def menu_claim(message: Message) -> None:
    await message.answer(texts.CLAIM_HINT)


async def _show_collection(bot: Bot, chat_id: int, user: User, ctx: Services, page: int, edit: Message | None) -> None:
    offset = page * kb.PAGE_SIZE
    cards, count, total = await ctx.game.user_cards(user.id, offset, kb.PAGE_SIZE)
    pages = max(1, math.ceil(count / kb.PAGE_SIZE))
    text = texts.collection(count, total, page, pages)
    markup = kb.collection_kb(cards, page, pages)
    if edit is not None:
        try:
            await edit.edit_text(text, reply_markup=markup)
            return
        except TelegramAPIError:
            pass
    await bot.send_message(chat_id, text, reply_markup=markup)


@router.message(Command("cards", "words"))
@router.message(F.text == kb.BTN_CARDS)
async def menu_cards(message: Message, user: User, ctx: Services, bot: Bot) -> None:
    await _show_collection(bot, message.chat.id, user, ctx, 0, None)


@router.callback_query(kb.PageCb.filter())
async def cb_page(callback: CallbackQuery, callback_data: kb.PageCb, user: User, ctx: Services, bot: Bot) -> None:
    await callback.answer()
    msg = callback.message
    await _show_collection(bot, msg.chat.id, user, ctx, max(0, callback_data.page), msg)  # type: ignore[union-attr, arg-type]


@router.message(Command("top"))
@router.message(F.text == kb.BTN_TOP)
async def menu_top(message: Message, ctx: Services) -> None:
    game = ctx.game
    await message.answer(
        texts.top(await game.top_lords(), await game.top_cards(), await game.top_fighters(), await game.world_size())
    )


@router.message(Command("profile", "me"))
@router.message(F.text == kb.BTN_PROFILE)
async def menu_profile(message: Message, user: User, ctx: Services) -> None:
    _, count, total = await ctx.game.user_cards(user.id, 0, 1)
    quills, battles = ctx.game.used_today(user)
    await message.answer(
        texts.profile(user, ctx.settings, count, total, quills, battles),
        reply_markup=kb.profile_kb(bool(user.sub_charge_id and is_lord(user)), user.sub_canceled),
    )


@router.message(Command("arena"))
@router.message(F.text == kb.BTN_ARENA)
async def menu_arena(message: Message, user: User, ctx: Services) -> None:
    cards, _, _ = await ctx.game.user_cards(user.id, 0, kb.PAGE_SIZE)
    if not cards:
        await message.answer(texts.NEED_CARD)
        return
    await message.answer(texts.ARENA, reply_markup=kb.arena_kb(cards))


# ---------- захват слова ----------


async def on_word(message: Message, user: User, ctx: Services, bot: Bot) -> None:
    """Any text that isn't a menu button or a command is a word (registered last, see the end of the file)."""
    raw = message.text or ""
    word = normalize(raw)
    if word is None:
        await message.answer(texts.NOT_A_WORD)
        return
    if not is_prompt_allowed(word):
        await message.answer(texts.FORBIDDEN_WORD)
        return
    display = display_form(raw)
    found = await ctx.game.lookup(word)
    if found.card is not None:
        await send_card(bot, message.chat.id, found.card, user.id, ctx)
        return
    if found.creating:
        await message.answer(texts.word_creating(display))
        return
    if found.reserved:
        auction = await ctx.auctions.current()
        await message.answer(texts.word_reserved(display, bool(auction and auction.word == word), ctx.settings))
        return
    quills, _ = ctx.game.used_today(user)
    left = max(0, ctx.game.daily_limit("quill", is_lord(user)) - quills)
    token = ctx.tokens.put(f"{word}\n{display}")
    price = ctx.settings.quill_price
    await message.answer(texts.word_free(display, left, price), reply_markup=kb.claim_kb(token, 0 if left else price))


@router.callback_query(kb.ClaimCb.filter())
async def cb_claim(callback: CallbackQuery, callback_data: kb.ClaimCb, user: User, ctx: Services, bot: Bot) -> None:
    stored = ctx.tokens.get(callback_data.token)
    if stored is None:
        await callback.answer("Запрос устарел — напиши слово ещё раз.", show_alert=True)
        return
    if user.id in ctx.busy:
        await callback.answer(texts.BUSY, show_alert=True)
        return
    chat_id = callback.message.chat.id  # type: ignore[union-attr]
    word, display = stored.split("\n", 1)
    if not await _gate(bot, chat_id, user, ctx):
        await callback.answer()
        return
    try:
        card_id, spend = await ctx.game.reserve(user.id, word, display)
    except GameError as e:
        await callback.answer()
        await send_error(bot, chat_id, e, ctx)
        return
    await callback.answer("✒️")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)  # type: ignore[union-attr]
    except TelegramAPIError:
        pass

    ctx.busy.add(user.id)
    try:
        status = await bot.send_message(chat_id, texts.creating(display, ctx.gen.load))
        me = await bot.me()
        try:
            created = await ctx.game.create_card(card_id, spend, is_lord(user), me.username or "")
        except GameError as e:
            await status.edit_text(texts.error_text(e, ctx.settings))
            return
        except Exception:
            await status.edit_text(texts.CREATE_FAILED)
            return
        card = created.card
        sent = await bot.send_photo(
            chat_id,
            BufferedInputFile(created.image, f"card_{card.id}.jpg"),
            caption=texts.card_caption(card, user, ctx.settings, user.id),
            reply_markup=kb.card_kb(card, user.id, ctx.game.shield_price(card), REDRAW_PRICE),
        )
        await _store_photo(ctx, card.id, sent)
        try:
            await status.delete()
        except TelegramAPIError:
            pass
        await bot.send_message(chat_id, texts.created(card))
        await reward_inviter(bot, ctx, user)
        if card.rarity in ("legendary", "mythic") and sent.photo:
            await announce(bot, ctx, texts.news_new_card(card, public_name(user)), sent.photo[-1].file_id)
    finally:
        ctx.busy.discard(user.id)


# ---------- действия с картой ----------


@router.callback_query(kb.CardCb.filter())
async def cb_card(callback: CallbackQuery, callback_data: kb.CardCb, user: User, ctx: Services, bot: Bot) -> None:
    chat_id = callback.message.chat.id  # type: ignore[union-attr]
    card = await ctx.game.get_card(callback_data.id)
    if card is None:
        await callback.answer(texts.ERRORS["not_found"], show_alert=True)
        return
    action = callback_data.action

    if action == "view":
        await callback.answer()
        await send_card(bot, chat_id, card, user.id, ctx)

    elif action in ("fight", "capture"):
        if card.owner_id == user.id:
            await callback.answer(texts.ERRORS["own_card"], show_alert=True)
            return
        mine, _, _ = await ctx.game.user_cards(user.id, 0, kb.PAGE_SIZE)
        if not mine:
            await callback.answer(texts.NEED_CARD, show_alert=True)
            return
        await callback.answer()
        capture = action == "capture"
        await bot.send_message(chat_id, texts.choose_fighter(card, capture), reply_markup=kb.fighters_kb(mine, card, capture))

    elif action == "offer":
        if card.owner_id == user.id:
            await callback.answer(texts.ERRORS["own_card"], show_alert=True)
            return
        await callback.answer()
        await bot.send_message(chat_id, texts.offer_choose(card), reply_markup=kb.offer_kb(card))

    elif action == "shield":
        try:
            until = await ctx.game.buy_shield(user.id, card.id)
        except GameError as e:
            await callback.answer()
            await send_error(bot, chat_id, e, ctx)
            return
        await callback.answer(texts.shield_bought(until, ctx.settings), show_alert=True)

    elif action == "redraw":
        if user.id in ctx.busy:
            await callback.answer(texts.BUSY, show_alert=True)
            return
        await callback.answer("🎨")
        ctx.busy.add(user.id)
        try:
            me = await bot.me()
            created = await ctx.game.redraw(user.id, card.id, is_lord(user), me.username or "")
            sent = await bot.send_photo(
                chat_id,
                BufferedInputFile(created.image, f"card_{card.id}.jpg"),
                caption=texts.card_caption(created.card, user, ctx.settings, user.id),
                reply_markup=kb.card_kb(created.card, user.id, ctx.game.shield_price(created.card), REDRAW_PRICE),
            )
            await _store_photo(ctx, card.id, sent)
        except GameError as e:
            await send_error(bot, chat_id, e, ctx)
        finally:
            ctx.busy.discard(user.id)
    else:
        await callback.answer()


# ---------- бои ----------


async def run_battle(
    callback: CallbackQuery, bot: Bot, user: User, mine: int, target: int, capture: bool, ctx: Services
) -> None:
    chat_id = callback.message.chat.id  # type: ignore[union-attr]
    if user.id in ctx.busy:
        await callback.answer(texts.BUSY, show_alert=True)
        return
    await callback.answer("⚔️")
    ctx.busy.add(user.id)
    try:
        async with ChatActionSender.typing(bot=bot, chat_id=chat_id):
            outcome = await ctx.game.battle(user.id, mine, target, capture)
    except GameError as e:
        await send_error(bot, chat_id, e, ctx)
        return
    finally:
        ctx.busy.discard(user.id)

    await bot.send_message(
        chat_id, texts.battle_result(outcome, ctx.settings), reply_markup=kb.after_battle_kb(outcome.defender, outcome.attacker)
    )
    if capture:
        attacker_name = public_name(user)
        await notify(
            bot,
            outcome.defender_user_id,
            texts.defender_notice(outcome, attacker_name),
            kb.card_link_kb(outcome.defender.id),
        )
        if outcome.captured:
            async with ctx.db.session() as s:
                defender = await repo.get_user(s, outcome.defender_user_id)
            await announce(
                bot, ctx, texts.news_capture(outcome.defender, attacker_name, public_name(defender)), outcome.defender.file_id
            )
    every = ctx.settings.ad_every
    if every > 0 and not is_lord(user) and (user.wins + user.losses + 1) % every == 0:
        ad = await ctx.kv.get(AD_TEXT)
        if ad:
            try:
                await bot.send_message(chat_id, texts.ad_block(ad))
            except TelegramAPIError:
                log.warning("Ad text has invalid HTML")


@router.callback_query(kb.FightCb.filter())
async def cb_fight(callback: CallbackQuery, callback_data: kb.FightCb, user: User, ctx: Services, bot: Bot) -> None:
    await run_battle(callback, bot, user, callback_data.mine, callback_data.target, callback_data.capture, ctx)


@router.callback_query(kb.ArenaCb.filter())
async def cb_arena(callback: CallbackQuery, callback_data: kb.ArenaCb, user: User, ctx: Services, bot: Bot) -> None:
    card = await ctx.game.get_card(callback_data.mine)
    if card is None or card.owner_id != user.id:
        await callback.answer(texts.ERRORS["not_owner"], show_alert=True)
        return
    opponent = await ctx.game.random_opponent(user.id, card)
    if opponent is None:
        await callback.answer(texts.NO_OPPONENTS, show_alert=True)
        return
    await run_battle(callback, bot, user, card.id, opponent.id, False, ctx)


# ---------- выкуп ----------


@router.callback_query(kb.OfferCb.filter())
async def cb_offer(callback: CallbackQuery, callback_data: kb.OfferCb, user: User, ctx: Services, bot: Bot) -> None:
    chat_id = callback.message.chat.id  # type: ignore[union-attr]
    try:
        offer = await ctx.game.make_offer(user.id, callback_data.card, callback_data.price)
    except GameError as e:
        await callback.answer()
        await send_error(bot, chat_id, e, ctx)
        return
    card = await ctx.game.get_card(offer.card_id)
    assert card is not None
    await callback.answer("📨")
    await bot.send_message(chat_id, texts.offer_sent(card, offer.price))
    await notify(
        bot, offer.seller_id, texts.offer_received(card, offer.price, public_name(user)), kb.offer_reply_kb(offer.id)
    )


@router.callback_query(kb.OfferReplyCb.filter())
async def cb_offer_reply(
    callback: CallbackQuery, callback_data: kb.OfferReplyCb, user: User, ctx: Services, bot: Bot
) -> None:
    msg = callback.message
    try:
        if callback_data.accept:
            result = await ctx.game.accept_offer(user.id, callback_data.id)
        else:
            declined = await ctx.game.decline_offer(user.id, callback_data.id)
    except GameError as e:
        await callback.answer(texts.error_text(e, ctx.settings), show_alert=True)
        return
    await callback.answer()

    if not callback_data.accept:
        await msg.edit_text("❌ Ты отказался от сделки.")  # type: ignore[union-attr]
        await notify(bot, declined.buyer_id, texts.offer_declined(declined.price))
        return
    if not result.ok or result.card is None:
        await msg.edit_text("Слово уже не у тебя — сделка отменена.")  # type: ignore[union-attr]
        await notify(bot, result.offer.buyer_id, texts.OFFER_CANCELED)
        return
    await msg.edit_text(texts.offer_accepted_seller(result.card, result.payout))  # type: ignore[union-attr]
    await notify(bot, result.offer.buyer_id, texts.offer_accepted_buyer(result.card))
    for other in result.canceled or []:
        await notify(bot, other.buyer_id, texts.OFFER_CANCELED)


# ---------- аукцион ----------


async def show_auction(bot: Bot, chat_id: int, user: User, ctx: Services) -> None:
    auction = await ctx.auctions.current()
    if auction is None:
        await bot.send_message(chat_id, texts.no_auction(ctx.settings))
        return
    leader = await ctx.auctions.winner(auction)
    min_bid = min_next_bid(auction, ctx.settings)
    await bot.send_message(
        chat_id,
        texts.auction_view(auction, public_name(leader) if leader else None, min_bid, ctx.settings, auction.top_bidder_id == user.id),
        reply_markup=kb.auction_kb(auction, min_bid),
    )


@router.message(Command("auction"))
@router.message(F.text == kb.BTN_AUCTION)
async def menu_auction(message: Message, user: User, ctx: Services, bot: Bot) -> None:
    await show_auction(bot, message.chat.id, user, ctx)


@router.callback_query(kb.MenuCb.filter(F.action == "auction"))
async def cb_auction(callback: CallbackQuery, user: User, ctx: Services, bot: Bot) -> None:
    await callback.answer()
    await show_auction(bot, callback.message.chat.id, user, ctx)  # type: ignore[union-attr]


async def place_bid(bot: Bot, chat_id: int, user: User, auction_id: int, amount: int, ctx: Services) -> None:
    try:
        result = await ctx.auctions.bid(user.id, auction_id, amount)
    except GameError as e:
        await send_error(bot, chat_id, e, ctx)
        return
    await bot.send_message(chat_id, texts.bid_ok(result.auction))
    if result.outbid_user_id:
        auction = result.auction
        await notify(
            bot,
            result.outbid_user_id,
            texts.outbid(auction, result.outbid_amount),
            kb.auction_kb(auction, min_next_bid(auction, ctx.settings)),
        )


@router.callback_query(kb.BidCb.filter())
async def cb_bid(callback: CallbackQuery, callback_data: kb.BidCb, user: User, ctx: Services, bot: Bot) -> None:
    await callback.answer()
    await place_bid(bot, callback.message.chat.id, user, callback_data.auction, callback_data.amount, ctx)  # type: ignore[union-attr]


@router.message(Command("bid"))
async def cmd_bid(message: Message, command: CommandObject, user: User, ctx: Services, bot: Bot) -> None:
    args = (command.args or "").split()
    auction = await ctx.auctions.current()
    if not args or not args[0].isdigit() or auction is None:
        await message.answer("Ставка: <code>/bid 500</code> (идёт ли аукцион — смотри /auction)")
        return
    await place_bid(bot, message.chat.id, user, auction.id, int(args[0]), ctx)


# ---------- прочее (регистрируется последним: порядок обработчиков важен) ----------

router.message.register(on_word, F.text & ~F.text.startswith("/"))


@router.message(F.text.startswith("/"))
async def on_unknown_command(message: Message) -> None:
    await message.answer("Не знаю такой команды 🤔 Правила — /rules")


@router.message(F.photo | F.voice | F.video | F.document | F.sticker | F.audio | F.video_note | F.animation)
async def on_other_content(message: Message) -> None:
    await message.answer(texts.ONLY_TEXT)
