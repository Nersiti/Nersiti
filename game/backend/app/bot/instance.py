from functools import lru_cache

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import get_settings


@lru_cache
def get_bot() -> Bot:
    return Bot(
        token=get_settings().bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


@lru_cache
def get_dispatcher() -> Dispatcher:
    from app.bot.handlers import build_router

    dp = Dispatcher()
    dp.include_router(build_router())
    return dp
