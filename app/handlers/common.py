from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, ChatMemberUpdated, Message

from app import keyboards as kb
from app import texts
from app.context import Services
from app.db import repo
from app.db.models import User
from app.services.growth import apply_start_payload

router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, user: User, is_new_user: bool, ctx: Services) -> None:
    payload = (command.args or "").strip()
    extra = await apply_start_payload(ctx, user, payload) if is_new_user and payload else None
    await message.answer(texts.welcome(user.first_name or "друг", ctx.settings), reply_markup=kb.main_kb())
    if extra:
        await message.answer(extra)


@router.message(Command("help"))
async def cmd_help(message: Message, ctx: Services) -> None:
    await message.answer(texts.help_text(ctx.settings))


@router.callback_query(kb.MenuCb.filter(F.action == "help"))
async def cb_help(callback: CallbackQuery, ctx: Services) -> None:
    await callback.message.answer(texts.help_text(ctx.settings))  # type: ignore[union-attr]
    await callback.answer()


@router.message(Command("terms", "privacy"))
async def cmd_terms(message: Message, ctx: Services) -> None:
    await message.answer(texts.terms(ctx.settings))


@router.message(Command("paysupport", "support"))
async def cmd_paysupport(message: Message, ctx: Services) -> None:
    await message.answer(texts.paysupport(ctx.settings))


@router.callback_query(kb.MenuCb.filter(F.action == "check_sub"))
async def cb_check_subscription(callback: CallbackQuery, user: User, ctx: Services) -> None:
    ctx.gate.forget(user.id)
    missing = await ctx.gate.missing(callback.bot, user.id)  # type: ignore[arg-type]
    if missing:
        await callback.answer(texts.SUBSCRIBE_STILL_MISSING, show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(texts.SUBSCRIBE_OK)  # type: ignore[union-attr]


@router.my_chat_member(F.chat.type == ChatType.PRIVATE)
async def on_my_chat_member(event: ChatMemberUpdated, ctx: Services) -> None:
    blocked = event.new_chat_member.status == ChatMemberStatus.KICKED
    async with ctx.db.begin() as s:
        await repo.set_fields(s, event.from_user.id, is_blocked=blocked)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message) -> None:
    await message.answer(texts.MAIN_MENU_HINT, reply_markup=kb.main_kb())


@router.message(Command("id"))
async def cmd_id(message: Message) -> None:
    await message.answer(f"Твой ID: <code>{message.from_user.id}</code>")  # type: ignore[union-attr]
