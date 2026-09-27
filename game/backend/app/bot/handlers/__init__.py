from aiogram import Router

from app.bot.handlers import admin, clans, groups, payments, settings, start


def build_router() -> Router:
    router = Router()
    router.include_router(payments.router)
    router.include_router(start.router)
    router.include_router(admin.router)
    router.include_router(clans.router)
    router.include_router(groups.router)
    router.include_router(settings.router)
    return router
