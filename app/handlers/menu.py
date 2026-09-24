from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app import keyboards as kb
from app import texts
from app.context import Services
from app.db import repo
from app.db.models import User
from app.services.images import RATIOS, STYLES

router = Router(name="menu")


@router.message(F.text == kb.BTN_CHAT)
async def menu_chat(message: Message, user: User, ctx: Services) -> None:
    async with ctx.db.begin() as s:
        await repo.set_fields(s, user.id, mode="chat")
    await message.answer(texts.chat_mode(), reply_markup=kb.chat_mode_kb())


@router.message(F.text == kb.BTN_IMAGE)
async def menu_image(message: Message, user: User, ctx: Services) -> None:
    async with ctx.db.begin() as s:
        await repo.set_fields(s, user.id, mode="image")
    await message.answer(texts.image_mode(user), reply_markup=kb.image_mode_kb())


@router.message(Command("profile", "me"))
@router.message(F.text == kb.BTN_PROFILE)
async def menu_profile(message: Message, user: User, ctx: Services) -> None:
    async with ctx.db.session() as s:
        referrals = await repo.count_referrals(s, user.id)
    await message.answer(
        texts.profile(user, ctx.settings, referrals),
        reply_markup=kb.profile_kb(bool(user.sub_charge_id and user.premium_until), user.sub_canceled),
    )


@router.message(Command("settings"))
@router.message(F.text == kb.BTN_SETTINGS)
async def menu_settings(message: Message, user: User) -> None:
    await message.answer(texts.settings_screen(user), reply_markup=kb.settings_kb())


@router.message(Command("new", "reset"))
async def cmd_new(message: Message, user: User, ctx: Services) -> None:
    async with ctx.db.begin() as s:
        await repo.clear_history(s, user.id)
        await repo.set_fields(s, user.id, mode="chat")
    await message.answer(texts.DIALOG_CLEARED)


@router.callback_query(kb.MenuCb.filter(F.action == "new"))
async def cb_new(callback: CallbackQuery, user: User, ctx: Services) -> None:
    async with ctx.db.begin() as s:
        await repo.clear_history(s, user.id)
        await repo.set_fields(s, user.id, mode="chat")
    await callback.answer("🧹 Новый диалог")
    await callback.message.answer(texts.DIALOG_CLEARED)  # type: ignore[union-attr]


@router.callback_query(kb.MenuCb.filter(F.action == "style"))
async def cb_styles(callback: CallbackQuery, user: User) -> None:
    await callback.message.answer(texts.CHOOSE_STYLE, reply_markup=kb.styles_kb(user.image_style))  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(kb.MenuCb.filter(F.action == "ratio"))
async def cb_ratios(callback: CallbackQuery, user: User) -> None:
    await callback.message.answer(texts.CHOOSE_RATIO, reply_markup=kb.ratios_kb(user.image_ratio))  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(kb.StyleCb.filter())
async def cb_set_style(callback: CallbackQuery, callback_data: kb.StyleCb, user: User, ctx: Services) -> None:
    if callback_data.code not in STYLES:
        await callback.answer()
        return
    async with ctx.db.begin() as s:
        await repo.set_fields(s, user.id, image_style=callback_data.code, mode="image")
    await callback.answer(f"Стиль: {STYLES[callback_data.code].label}")
    try:
        await callback.message.edit_reply_markup(reply_markup=kb.styles_kb(callback_data.code))  # type: ignore[union-attr]
    except TelegramBadRequest:
        pass


@router.callback_query(kb.RatioCb.filter())
async def cb_set_ratio(callback: CallbackQuery, callback_data: kb.RatioCb, user: User, ctx: Services) -> None:
    if callback_data.code not in RATIOS:
        await callback.answer()
        return
    async with ctx.db.begin() as s:
        await repo.set_fields(s, user.id, image_ratio=callback_data.code, mode="image")
    await callback.answer(f"Формат: {RATIOS[callback_data.code][0]}")
    try:
        await callback.message.edit_reply_markup(reply_markup=kb.ratios_kb(callback_data.code))  # type: ignore[union-attr]
    except TelegramBadRequest:
        pass
