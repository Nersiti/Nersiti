from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatType

from app.handlers import admin, bonus, common, game, inline, payments


def setup_routers() -> Router:
    private = Router(name="private")
    # Игра идёт в личных сообщениях; оплаты (pre_checkout) приходят без чата.
    private.message.filter(F.chat.type == ChatType.PRIVATE)
    private.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)
    # Порядок важен: админ-команды → общие → оплата → бонусы → игра (ловит весь остальной текст как слова).
    private.include_routers(admin.router, common.router, payments.router, bonus.router, game.router)

    root = Router(name="root")
    root.include_routers(private, inline.router, inline.group_router)
    return root


ALL_ROUTERS = (admin.router, common.router, payments.router, bonus.router, game.router, inline.router, inline.group_router)
