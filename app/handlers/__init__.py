from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatType

from app.handlers import admin, ai, bonus, common, menu, payments


def setup_routers() -> Router:
    root = Router(name="root")
    # Бот работает только в личных сообщениях; оплаты (pre_checkout) приходят без чата.
    root.message.filter(F.chat.type == ChatType.PRIVATE)
    root.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)
    # Порядок важен: админ-команды → общие → оплата → бонусы → меню → ИИ (ловит весь остальной текст).
    root.include_routers(admin.router, common.router, payments.router, bonus.router, menu.router, ai.router)
    return root
