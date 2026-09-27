import html

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from app.config import get_settings
from app.db import get_sessionmaker
from app.game import clan_service
from app.i18n import pick_lang, t
from app.models import Clan

router = Router()


@router.my_chat_member()
async def on_bot_membership(update: ChatMemberUpdated) -> None:
    """If the bot loses access to a clan chat, subscriptions can no longer be verified."""
    if update.new_chat_member.status not in ("left", "kicked"):
        return
    async with get_sessionmaker()() as session:
        clan = (
            await session.execute(select(Clan).where(Clan.tg_chat_id == update.chat.id))
        ).scalar_one_or_none()
        if clan is not None and clan.subscribers_only:
            clan.subscribers_only = False
            await session.commit()


@router.message(Command("clan"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_clan_in_group(message: Message) -> None:
    lang = pick_lang(message.from_user.language_code if message.from_user else None)
    async with get_sessionmaker()() as session:
        clan = (
            await session.execute(select(Clan).where(Clan.tg_chat_id == message.chat.id))
        ).scalar_one_or_none()
        if clan is None or clan.banned:
            await message.reply(t(lang, "clan.group.none"))
            return
        text = t(
            lang,
            "clan.group.status",
            title=html.escape(clan.title),
            members=clan.members_count,
            sectors=await clan_service.sectors_held(session, clan.id),
            points=clan.season_points,
            rank=await clan_service.clan_rank(session, clan),
        )
    link = clan_service.start_link(get_settings().bot_username, clan.id)
    await message.reply(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=t(lang, "clan.group.button"), url=link)]]
        ),
    )
