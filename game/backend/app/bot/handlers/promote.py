"""/promote: channel admins buy a sponsored "subscribe" task for Telegram Stars."""

import html
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    KeyboardButtonRequestChat,
    LabeledPrice,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from app.bot.handlers.clans import _rights
from app.config import get_settings
from app.db import get_sessionmaker
from app.game import economy, promo_service
from app.game.errors import GameError
from app.i18n import pick_lang, t

log = logging.getLogger(__name__)
router = Router()

REQUEST_PROMO_CHANNEL = 3


class PromoCb(CallbackData, prefix="promo"):
    action: str  # "pkg" | "approve" | "reject"
    value: int


def _lang(user) -> str:
    return pick_lang(user.language_code if user else None)


@router.message(Command("promote"), F.chat.type == "private")
async def cmd_promote(message: Message) -> None:
    lang = _lang(message.from_user)
    packages = "\n".join(
        t(lang, "promote.package", subs=subs, stars=stars) for subs, stars in economy.PROMO_PACKAGES
    )
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text=t(lang, "promote.pick_channel"),
                    request_chat=KeyboardButtonRequestChat(
                        request_id=REQUEST_PROMO_CHANNEL,
                        chat_is_channel=True,
                        user_administrator_rights=_rights(channel=True),
                        bot_administrator_rights=_rights(channel=True),
                        request_title=True,
                        request_username=True,
                    ),
                )
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer(t(lang, "promote.intro", packages=packages), reply_markup=keyboard)


@router.message(F.chat_shared.request_id == REQUEST_PROMO_CHANNEL, F.chat.type == "private")
async def on_promo_channel(message: Message, bot: Bot) -> None:
    shared = message.chat_shared
    lang = _lang(message.from_user)
    remove = ReplyKeyboardRemove()
    try:
        user_member = await bot.get_chat_member(shared.chat_id, message.from_user.id)
        bot_member = await bot.get_chat_member(shared.chat_id, bot.id)
        if user_member.status not in ("creator", "administrator"):
            await message.answer(t(lang, "newclan.not_admin"), reply_markup=remove)
            return
        if bot_member.status != "administrator":
            await message.answer(t(lang, "newclan.bot_not_admin"), reply_markup=remove)
            return
        title = shared.title or str(shared.chat_id)
        if shared.username:
            url = f"https://t.me/{shared.username}"
        else:
            url = (
                await bot.create_chat_invite_link(chat_id=shared.chat_id, name="World Battle")
            ).invite_link
    except TelegramAPIError as exc:
        log.warning("promote check failed: %s", exc)
        await message.answer(t(lang, "newclan.error"), reply_markup=remove)
        return

    await promo_service.save_selection(message.from_user.id, shared.chat_id, title, url)
    buttons = [
        [
            InlineKeyboardButton(
                text=t(lang, "promote.button", subs=subs, stars=stars),
                callback_data=PromoCb(action="pkg", value=idx).pack(),
            )
        ]
        for idx, (subs, stars) in enumerate(economy.PROMO_PACKAGES)
    ]
    await message.answer("✅", reply_markup=remove)
    await message.answer(
        t(lang, "promote.choose", title=html.escape(title)),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(PromoCb.filter(F.action == "pkg"))
async def on_package(callback: CallbackQuery, callback_data: PromoCb, bot: Bot) -> None:
    lang = _lang(callback.from_user)
    selection = await promo_service.get_selection(callback.from_user.id)
    if selection is None:
        await callback.answer(t(lang, "promote.expired"), show_alert=True)
        return
    subs, stars = promo_service.package(callback_data.value)
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=t(lang, "promote.invoice.title", subs=subs),
        description=t(lang, "promote.invoice.desc", title=selection["title"], subs=subs)[:255],
        payload=promo_service.build_payload(
            callback.from_user.id, selection["chat_id"], callback_data.value
        ),
        currency="XTR",
        prices=[LabeledPrice(label=t(lang, "promote.invoice.title", subs=subs), amount=stars)],
    )
    await callback.answer()


async def notify_admins(bot: Bot, task, sponsor_name: str) -> None:
    for admin_id in get_settings().admin_id_set:
        lang = "ru"
        text = t(
            lang,
            "promote.admin.new",
            task=task.id,
            title=html.escape(task.title_ru),
            url=task.url,
            subs=task.max_completions,
            stars=task.stars_paid,
            sponsor=html.escape(sponsor_name),
        )
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=t(lang, "promote.admin.approve"),
                        callback_data=PromoCb(action="approve", value=task.id).pack(),
                    ),
                    InlineKeyboardButton(
                        text=t(lang, "promote.admin.reject"),
                        callback_data=PromoCb(action="reject", value=task.id).pack(),
                    ),
                ]
            ]
        )
        try:
            await bot.send_message(
                admin_id, text, reply_markup=markup, disable_web_page_preview=True
            )
        except TelegramAPIError as exc:
            log.warning("could not notify admin %s: %s", admin_id, exc)


@router.callback_query(PromoCb.filter(F.action.in_({"approve", "reject"})))
async def on_moderation(callback: CallbackQuery, callback_data: PromoCb, bot: Bot) -> None:
    lang = _lang(callback.from_user)
    if callback.from_user.id not in get_settings().admin_id_set:
        await callback.answer(t(lang, "admin.only"), show_alert=True)
        return
    async with get_sessionmaker()() as session:
        try:
            if callback_data.action == "approve":
                task = await promo_service.approve(session, callback_data.value)
                sponsor_key = "promote.approved"
            else:
                task = await promo_service.reject(session, bot, callback_data.value)
                sponsor_key = "promote.rejected"
            await session.commit()
        except (GameError, TelegramAPIError) as exc:
            await session.rollback()
            await callback.answer(getattr(exc, "code", str(exc)), show_alert=True)
            return
    await callback.answer(t(lang, "promote.admin.done", task=task.id, status=task.status))
    if task.sponsor_user_id:
        try:
            await bot.send_message(task.sponsor_user_id, t("ru", sponsor_key))
        except TelegramAPIError:
            pass
    if callback.message is not None:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except TelegramAPIError:
            pass
