from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand, BufferedInputFile, ErrorEvent
from sqlalchemy import select

from app import keyboards as kb
from app import texts
from app.config import Settings
from app.context import Services
from app.db.database import Database
from app.db.models import Auction, Card
from app.game.auction import AUCTION_RARITIES, AuctionService
from app.game.service import REDRAW_PRICE, GameService, public_name
from app.handlers import setup_routers
from app.middlewares import ThrottlingMiddleware, UserMiddleware
from app.services.channels import ChannelGate
from app.services.growth import announce, notify
from app.services.images import create_image_backend
from app.services.kv import KVStore
from app.services.llm import create_llm
from app.services.payments.service import PaymentService
from app.services.payments.yookassa import YooKassaClient
from app.services.queue import GenerationQueue

if TYPE_CHECKING:
    from app.db.models import User

log = logging.getLogger(__name__)

LOOP_INTERVAL = 30.0

USER_COMMANDS = [
    BotCommand(command="start", description="🏠 Главное меню"),
    BotCommand(command="cards", description="🃏 Мои слова"),
    BotCommand(command="arena", description="⚔️ Арена"),
    BotCommand(command="auction", description="🔨 Аукцион дня"),
    BotCommand(command="top", description="🏆 Топ мира слов"),
    BotCommand(command="buy", description="💎 Магазин"),
    BotCommand(command="bonus", description="🎁 Бесплатные кристаллы"),
    BotCommand(command="profile", description="👤 Профиль"),
    BotCommand(command="rules", description="📖 Правила"),
    BotCommand(command="terms", description="📄 Условия"),
    BotCommand(command="paysupport", description="🛟 Поддержка по оплате"),
]

SHORT_DESCRIPTION = "Игра, где можно навсегда завладеть любым словом мира. Захвати своё, пока не забрали 👀"
DESCRIPTION = (
    "✒️ Напиши любое слово — если оно свободно, оно твоё навсегда.\n"
    "🧠 Нейросеть превращает слово в уникальное существо и рисует карту.\n"
    "⚔️ Сражайся, захватывай чужие слова, выкупай и защищай свои.\n"
    "🔨 Каждый день — аукцион легендарного слова.\n\n"
    "Нажми «Запустить» 👇"
)


def build_services(settings: Settings) -> Services:
    db = Database(settings.database_url)
    kv = KVStore(db)
    llm = create_llm(settings)
    images = create_image_backend(settings)
    gen = GenerationQueue(settings.image_workers)
    yookassa = None
    if settings.yookassa_enabled:
        yookassa = YooKassaClient(
            settings.yookassa_shop_id,
            settings.yookassa_secret_key.get_secret_value(),
            settings.yookassa_return_url or "https://t.me/",
            settings.yookassa_receipt_email,
            settings.rub_vat_code,
        )
    game = GameService(db, settings, llm, images, gen)
    return Services(
        settings=settings,
        db=db,
        kv=kv,
        llm=llm,
        images=images,
        gen=gen,
        payments=PaymentService(db, settings, yookassa),
        gate=ChannelGate(settings, kv),
        game=game,
        auctions=AuctionService(db, settings, game),
    )


def build_dispatcher(ctx: Services) -> Dispatcher:
    dp = Dispatcher()
    dp["ctx"] = ctx
    dp.update.outer_middleware(UserMiddleware(ctx))
    dp.message.middleware(ThrottlingMiddleware(ctx.settings.throttle_seconds))
    dp.include_router(setup_routers())

    @dp.errors()
    async def on_error(event: ErrorEvent) -> bool:
        log.exception("Unhandled error: %r", event.exception, exc_info=event.exception)
        return True

    async def on_startup(bot: Bot) -> None:
        await startup(bot, ctx)

    async def on_shutdown(bot: Bot) -> None:
        await shutdown(ctx)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    return dp


# ---------- фоновые задачи ----------


async def award_auction(bot: Bot, ctx: Services, auction: Auction, winner: User) -> None:
    """Create the legendary card for the auction winner."""
    async with ctx.db.session() as s:
        existing = await s.scalar(select(Card).where(Card.word == auction.word))
    if existing is not None:
        if existing.owner_id == winner.id:
            if existing.status == "active":
                await ctx.auctions.attach_card(auction.id, existing.id)
            return  # карта уже создаётся или создана
        if await ctx.auctions.refund_winner(auction):
            await notify(bot, winner.id, texts.auction_refunded(auction.display, auction.top_bid))
        return
    card_id = await ctx.game.reserve_for_auction(winner.id, auction.word, auction.display)
    me = await bot.me()
    created = await ctx.game.create_card(card_id, None, True, me.username or "", rarities=AUCTION_RARITIES)
    await ctx.auctions.attach_card(auction.id, card_id)
    card = created.card
    try:
        sent = await bot.send_photo(
            winner.id,
            BufferedInputFile(created.image, f"card_{card.id}.jpg"),
            caption=texts.card_caption(card, winner, ctx.settings, winner.id),
            reply_markup=kb.card_kb(card, winner.id, ctx.game.shield_price(card), REDRAW_PRICE),
        )
        if sent.photo:
            await ctx.game.set_file_id(card.id, sent.photo[-1].file_id)
            card.file_id = sent.photo[-1].file_id
    except TelegramAPIError as e:
        log.warning("Can't send auction card to %s: %s", winner.id, e)
    await notify(bot, winner.id, texts.auction_won(card, auction.top_bid))
    await announce(bot, ctx, texts.news_auction_won(card, auction.top_bid, public_name(winner)), card.file_id)


async def game_tick(bot: Bot, ctx: Services) -> None:
    await ctx.game.cleanup_stale()
    await ctx.auctions.close_due()
    async with ctx.db.session() as s:
        pending = (
            await s.scalars(select(Auction).where(Auction.status == "finished", Auction.card_id.is_(None)))
        ).all()
    for auction in pending:
        winner = await ctx.auctions.winner(auction)
        if winner is not None:
            try:
                await award_auction(bot, ctx, auction, winner)
            except Exception:
                log.exception("Auction %s award failed, will retry", auction.id)
    started = await ctx.auctions.maybe_start_daily()
    if started is not None:
        await announce(bot, ctx, texts.news_auction_start(started, ctx.settings))
    for offer in await ctx.game.expire_offers():
        await notify(bot, offer.buyer_id, texts.offer_expired(offer.price))


async def game_loop(bot: Bot, ctx: Services) -> None:
    while True:
        try:
            await game_tick(bot, ctx)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Game loop tick failed")
        await asyncio.sleep(LOOP_INTERVAL)


# ---------- запуск ----------


async def startup(bot: Bot, ctx: Services, configure_bot: bool = True, background: bool = True) -> None:
    await ctx.db.create_all()
    ctx.gen.start()
    if background:
        ctx.tasks.append(asyncio.create_task(game_loop(bot, ctx), name="game-loop"))
        if ctx.payments.yookassa is not None:
            ctx.tasks.append(asyncio.create_task(ctx.payments.poll_yookassa(bot), name="yookassa-poll"))
    if configure_bot:
        try:
            await bot.set_my_commands(USER_COMMANDS)
            await bot.set_my_short_description(SHORT_DESCRIPTION)
            await bot.set_my_description(DESCRIPTION)
        except TelegramAPIError as e:
            log.warning("Can't update bot profile: %s", e)
    me = await bot.me()
    log.info("Bot @%s started. Payment methods: %s", me.username, ctx.payments.methods())


async def shutdown(ctx: Services) -> None:
    for task in list(ctx.tasks):
        task.cancel()
    await asyncio.gather(*ctx.tasks, return_exceptions=True)
    await ctx.gen.stop()
    await ctx.llm.close()
    await ctx.images.close()
    if ctx.payments.yookassa is not None:
        await ctx.payments.yookassa.close()
    await ctx.db.close()


def create_bot(settings: Settings) -> Bot:
    return Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )


async def run(settings: Settings) -> None:
    ctx = build_services(settings)
    bot = create_bot(settings)
    dp = build_dispatcher(ctx)
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
