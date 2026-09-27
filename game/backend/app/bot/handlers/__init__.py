from aiogram import Router

from app.bot.handlers import clans, groups, start


def build_router() -> Router:
    router = Router()
    router.include_router(start.router)
    router.include_router(clans.router)
    router.include_router(groups.router)
    return router
