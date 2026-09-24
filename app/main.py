from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand, ErrorEvent

from app.config import Settings
from app.context import Services
from app.db import repo
from app.db.database import Database
from app.handlers import setup_routers
from app.middlewares import ThrottlingMiddleware, UserMiddleware
from app.services.channels import ChannelGate
from app.services.growth import showcase_loop
from app.services.images import create_image_backend
from app.services.kv import KVStore
from app.services.llm import create_llm
from app.services.payments.service import PaymentService
from app.services.payments.yookassa import YooKassaClient
from app.services.queue import GenerationQueue

log = logging.getLogger(__name__)

USER_COMMANDS = [
    BotCommand(command="start", description="🏠 Главное меню"),
    BotCommand(command="new", description="🧹 Новый диалог"),
    BotCommand(command="img", description="🎨 Нарисовать картинку"),
    BotCommand(command="buy", description="💎 Premium и кредиты"),
    BotCommand(command="bonus", description="🎁 Бесплатные кредиты"),
    BotCommand(command="profile", description="👤 Профиль и лимиты"),
    BotCommand(command="help", description="❓ Помощь"),
    BotCommand(command="terms", description="📄 Условия"),
    BotCommand(command="paysupport", description="🛟 Поддержка по оплате"),
]

SHORT_DESCRIPTION = "ИИ-чат и генерация картинок прямо в Telegram. Бесплатно каждый день 🎁"
DESCRIPTION = (
    "🤖 Нейросеть в Telegram:\n"
    "💬 отвечает на любые вопросы — учёба, работа, код, тексты\n"
    "🎨 рисует картинки по описанию на русском\n"
    "🎁 бесплатные запросы каждый день\n\n"
    "Нажми «Запустить» 👇"
)


def build_services(settings: Settings) -> Services:
    db = Database(settings.database_url)
    kv = KVStore(db)
    yookassa = None
    if settings.yookassa_enabled:
        yookassa = YooKassaClient(
            settings.yookassa_shop_id,
            settings.yookassa_secret_key.get_secret_value(),
            settings.yookassa_return_url or "https://t.me/",
            settings.yookassa_receipt_email,
            settings.rub_vat_code,
        )
    return Services(
        settings=settings,
        db=db,
        kv=kv,
        llm=create_llm(settings),
        images=create_image_backend(settings),
        gen=GenerationQueue(settings.image_workers),
        payments=PaymentService(db, settings, yookassa),
        gate=ChannelGate(settings, kv),
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


async def startup(bot: Bot, ctx: Services, configure_bot: bool = True) -> None:
    await ctx.db.create_all()
    async with ctx.db.begin() as s:
        await repo.prune_usage(s)
    ctx.gen.start()
    if ctx.payments.yookassa is not None:
        ctx.tasks.append(asyncio.create_task(ctx.payments.poll_yookassa(bot), name="yookassa-poll"))
    if ctx.settings.showcase_channel:
        ctx.tasks.append(asyncio.create_task(showcase_loop(bot, ctx), name="showcase"))
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
