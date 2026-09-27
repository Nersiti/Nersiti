from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.db import get_sessionmaker
from app.i18n import pick_lang, t
from app.models import User

router = Router()
TOGGLE = "settings:notify"


def _view(user: User, lang: str) -> tuple[str, InlineKeyboardMarkup]:
    text = t(
        lang,
        "settings.text",
        state=t(lang, "settings.on" if user.notify_enabled else "settings.off"),
    )
    button = InlineKeyboardButton(
        text=t(lang, "settings.toggle_off" if user.notify_enabled else "settings.toggle_on"),
        callback_data=TOGGLE,
    )
    return text, InlineKeyboardMarkup(inline_keyboard=[[button]])


@router.message(Command("settings"), F.chat.type == "private")
async def cmd_settings(message: Message) -> None:
    lang = pick_lang(message.from_user.language_code)
    async with get_sessionmaker()() as session:
        user = await session.get(User, message.from_user.id)
    if user is None:
        await message.answer(t(lang, "settings.need_start"))
        return
    text, markup = _view(user, lang)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data == TOGGLE)
async def on_toggle(callback: CallbackQuery) -> None:
    lang = pick_lang(callback.from_user.language_code)
    async with get_sessionmaker()() as session:
        user = await session.get(User, callback.from_user.id, with_for_update=True)
        if user is None:
            await callback.answer(t(lang, "settings.need_start"), show_alert=True)
            return
        user.notify_enabled = not user.notify_enabled
        await session.commit()
    text, markup = _view(user, lang)
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(text, reply_markup=markup)
