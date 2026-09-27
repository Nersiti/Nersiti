import re

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from app.config import get_settings
from app.i18n import pick_lang, t

router = Router()
router.message.filter(F.chat.type == "private")

START_PARAM_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def play_keyboard(lang: str, start_param: str | None = None) -> InlineKeyboardMarkup:
    url = get_settings().webapp_url
    if start_param and START_PARAM_RE.match(start_param):
        # The Mini App reads ?sp= when it was opened from the bot chat
        # (initData has no start_param in that case).
        url = f"{url}?sp={start_param}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "start.button"), web_app=WebAppInfo(url=url))]
        ]
    )


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject) -> None:
    lang = pick_lang(message.from_user.language_code if message.from_user else None)
    await message.answer(
        t(lang, "start.greeting", game=get_settings().game_name),
        reply_markup=play_keyboard(lang, command.args),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    lang = pick_lang(message.from_user.language_code if message.from_user else None)
    await message.answer(t(lang, "help.text", game=get_settings().game_name))


@router.message(Command("terms"))
async def cmd_terms(message: Message) -> None:
    lang = pick_lang(message.from_user.language_code if message.from_user else None)
    await message.answer(t(lang, "terms.text"))


@router.message(Command("privacy"))
async def cmd_privacy(message: Message) -> None:
    lang = pick_lang(message.from_user.language_code if message.from_user else None)
    await message.answer(t(lang, "privacy.text"))


@router.message(Command("paysupport"))
async def cmd_paysupport(message: Message) -> None:
    lang = pick_lang(message.from_user.language_code if message.from_user else None)
    await message.answer(t(lang, "paysupport.text"))
