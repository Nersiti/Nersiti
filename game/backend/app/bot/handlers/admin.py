"""Admin commands (Telegram ids listed in ADMIN_IDS)."""

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.config import get_settings
from app.db import get_sessionmaker
from app.game import shop_service
from app.game.errors import GameError
from app.i18n import pick_lang, t

router = Router()
router.message.filter(F.chat.type == "private")


def is_admin(message: Message) -> bool:
    return message.from_user is not None and message.from_user.id in get_settings().admin_id_set


@router.message(Command("refund"))
async def cmd_refund(message: Message, command: CommandObject, bot: Bot) -> None:
    lang = pick_lang(message.from_user.language_code if message.from_user else None)
    if not is_admin(message):
        await message.answer(t(lang, "admin.only"))
        return
    charge_id = (command.args or "").strip()
    if not charge_id:
        await message.answer(t(lang, "admin.refund.usage"))
        return
    async with get_sessionmaker()() as session:
        try:
            payment = await shop_service.refund(session, bot, charge_id)
            await session.commit()
        except (GameError, TelegramAPIError) as exc:
            await session.rollback()
            await message.answer(
                t(lang, "admin.refund.failed", error=getattr(exc, "code", str(exc)))
            )
            return
    await message.answer(t(lang, "admin.refund.done", stars=payment.stars, user=payment.user_id))
