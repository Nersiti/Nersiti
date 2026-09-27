import html
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    CallbackQuery,
    ChatAdministratorRights,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    KeyboardButtonRequestChat,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from app.config import get_settings
from app.db import get_sessionmaker
from app.game import clan_service
from app.i18n import pick_lang, t
from app.models import Clan
from app.moderation import is_allowed

log = logging.getLogger(__name__)
router = Router()

REQUEST_CHANNEL = 1
REQUEST_GROUP = 2


class ClanCb(CallbackData, prefix="clan"):
    action: str  # "post" | "subs"
    clan_id: int


def _rights(channel: bool) -> ChatAdministratorRights:
    return ChatAdministratorRights(
        is_anonymous=False,
        can_manage_chat=True,
        can_delete_messages=False,
        can_manage_video_chats=False,
        can_restrict_members=False,
        can_promote_members=False,
        can_change_info=False,
        can_invite_users=True,
        can_post_stories=False,
        can_edit_stories=False,
        can_delete_stories=False,
        can_send_welcome_messages=False,
        can_post_messages=True if channel else None,
    )


def newclan_keyboard(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text=t(lang, "newclan.channel"),
                    request_chat=KeyboardButtonRequestChat(
                        request_id=REQUEST_CHANNEL,
                        chat_is_channel=True,
                        user_administrator_rights=_rights(channel=True),
                        bot_administrator_rights=_rights(channel=True),
                        request_title=True,
                        request_username=True,
                    ),
                )
            ],
            [
                KeyboardButton(
                    text=t(lang, "newclan.group"),
                    request_chat=KeyboardButtonRequestChat(
                        request_id=REQUEST_GROUP,
                        chat_is_channel=False,
                        bot_is_member=True,
                        request_title=True,
                        request_username=True,
                    ),
                )
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


async def send_newclan_prompt(message: Message) -> None:
    lang = pick_lang(message.from_user.language_code if message.from_user else None)
    await message.answer(
        t(
            lang,
            "newclan.intro",
            min_channel=clan_service.MIN_MEMBERS[clan_service.CHANNEL],
            min_group=clan_service.MIN_MEMBERS[clan_service.GROUP],
        ),
        reply_markup=newclan_keyboard(lang),
    )


def settings_keyboard(clan: Clan, lang: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=t(lang, "clan.btn.post"),
                callback_data=ClanCb(action="post", clan_id=clan.id).pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text=t(lang, "clan.btn.subs_on" if clan.subscribers_only else "clan.btn.subs_off"),
                callback_data=ClanCb(action="subs", clan_id=clan.id).pack(),
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("newclan"), F.chat.type == "private")
async def cmd_newclan(message: Message) -> None:
    await send_newclan_prompt(message)


@router.message(
    F.chat_shared.request_id.in_({REQUEST_CHANNEL, REQUEST_GROUP}), F.chat.type == "private"
)
async def on_chat_shared(message: Message, bot: Bot) -> None:
    shared = message.chat_shared
    user = message.from_user
    lang = pick_lang(user.language_code if user else None)
    kind = clan_service.CHANNEL if shared.request_id == REQUEST_CHANNEL else clan_service.GROUP
    remove = ReplyKeyboardRemove()

    try:
        user_member = await bot.get_chat_member(shared.chat_id, user.id)
        bot_member = await bot.get_chat_member(shared.chat_id, bot.id)
        count = await bot.get_chat_member_count(shared.chat_id)
        title = shared.title
        username = shared.username
        if not title:
            chat = await bot.get_chat(shared.chat_id)
            title, username = chat.title or str(shared.chat_id), chat.username
    except TelegramAPIError as exc:
        log.warning("newclan check failed for chat %s: %s", shared.chat_id, exc)
        await message.answer(t(lang, "newclan.error"), reply_markup=remove)
        return

    if user_member.status not in ("creator", "administrator"):
        await message.answer(t(lang, "newclan.not_admin"), reply_markup=remove)
        return
    bot_ok = ("administrator",) if kind == clan_service.CHANNEL else ("administrator", "member")
    if bot_member.status not in bot_ok:
        await message.answer(t(lang, "newclan.bot_not_admin"), reply_markup=remove)
        return
    if count < clan_service.MIN_MEMBERS[kind]:
        await message.answer(
            t(lang, "newclan.too_small", n=clan_service.MIN_MEMBERS[kind]), reply_markup=remove
        )
        return
    if not is_allowed(title):
        await message.answer(t(lang, "newclan.bad_title"), reply_markup=remove)
        return

    async with get_sessionmaker()() as session:
        clan, created = await clan_service.upsert_chat_clan(
            session,
            kind=kind,
            chat_id=shared.chat_id,
            title=title,
            username=username,
            owner_user_id=user.id,
        )
        await session.commit()

    link = clan_service.start_link(get_settings().bot_username, clan.id)
    safe_title = html.escape(clan.title)
    await message.answer(
        t(lang, "newclan.created" if created else "newclan.updated", title=safe_title, link=link),
        reply_markup=remove,
        disable_web_page_preview=True,
    )
    await message.answer(
        t(lang, "clan.settings", title=safe_title), reply_markup=settings_keyboard(clan, lang)
    )


@router.callback_query(ClanCb.filter())
async def on_clan_settings(callback: CallbackQuery, callback_data: ClanCb, bot: Bot) -> None:
    lang = pick_lang(callback.from_user.language_code)
    async with get_sessionmaker()() as session:
        clan = await session.get(Clan, callback_data.clan_id, with_for_update=True)
        if clan is None or clan.owner_user_id != callback.from_user.id:
            await callback.answer(t(lang, "clan.not_owner"), show_alert=True)
            return

        if callback_data.action == "post":
            link = clan_service.start_link(get_settings().bot_username, clan.id)
            try:
                await bot.send_message(
                    chat_id=clan.tg_chat_id,
                    text=t(
                        lang,
                        "clan.post.text",
                        title=html.escape(clan.title),
                        game=get_settings().game_name,
                    ),
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text=t(lang, "clan.post.button"), url=link)]
                        ]
                    ),
                )
            except TelegramAPIError as exc:
                log.info("Clan %s post failed: %s", clan.id, exc)
                await callback.answer(t(lang, "clan.post.failed"), show_alert=True)
                return
            await callback.answer(t(lang, "clan.post.done"))
            return

        if callback_data.action == "subs":
            clan.subscribers_only = not clan.subscribers_only
            if clan.subscribers_only and not clan.username and not clan.invite_link:
                try:
                    invite = await bot.create_chat_invite_link(
                        chat_id=clan.tg_chat_id, name=get_settings().game_name[:32]
                    )
                    clan.invite_link = invite.invite_link
                except TelegramAPIError as exc:
                    log.info("Clan %s invite link failed: %s", clan.id, exc)
            await session.commit()
            await callback.answer(t(lang, "clan.subs.changed"))
            if callback.message is not None:
                try:
                    await callback.message.edit_reply_markup(
                        reply_markup=settings_keyboard(clan, lang)
                    )
                except TelegramAPIError:
                    pass
