"""Main feature: AI chat and image generation."""

from __future__ import annotations

import logging
import random
import time
from contextlib import aclosing

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.chat_action import ChatActionSender

from app import keyboards as kb
from app import texts
from app.context import Services
from app.db import repo
from app.db.models import User
from app.services import billing
from app.services.billing import Charge, Kind, is_premium
from app.services.formatting import md_to_html, split_text, strip_think
from app.services.growth import reward_inviter
from app.services.images import build_request
from app.services.kv import AD_TEXT
from app.services.llm import Messages, to_image_prompt
from app.services.moderation import is_prompt_allowed
from app.services.queue import PRIORITY_FREE, PRIORITY_PREMIUM
from app.utils import has_cyrillic

log = logging.getLogger(__name__)
router = Router(name="ai")

DRAFT_INTERVAL = 0.8  # секунд между обновлениями «печатающегося» ответа
MAX_INPUT = 4000


# ---------- общие проверки ----------


async def _precheck(bot: Bot, chat_id: int, user: User, ctx: Services) -> bool:
    if user.id in ctx.busy:
        await bot.send_message(chat_id, texts.BUSY)
        return False
    if not is_premium(user) and not ctx.settings.is_admin(user.id):
        missing = await ctx.gate.missing(bot, user.id)
        if missing:
            await bot.send_message(chat_id, texts.SUBSCRIBE_REQUIRED, reply_markup=kb.channels_kb(missing))
            return False
    return True


async def _charge(bot: Bot, chat_id: int, user: User, kind: Kind, ctx: Services) -> Charge | None:
    async with ctx.db.begin() as s:
        ch = await billing.charge(s, user.id, kind, ctx.settings)
    if not ch.ok:
        await bot.send_message(chat_id, texts.no_funds(kind, ctx.settings, ch.premium), reply_markup=kb.no_funds_kb())
        return None
    return ch


async def _refund(ctx: Services, user: User, ch: Charge) -> None:
    async with ctx.db.begin() as s:
        await billing.refund(s, user.id, ch)


async def _after_success(bot: Bot, chat_id: int, user: User, ch: Charge, ctx: Services) -> None:
    await reward_inviter(bot, ctx, user)
    if ch.premium:
        return
    if ch.source == "free" and ch.remaining is not None and ch.remaining <= 2:
        await bot.send_message(chat_id, texts.quota_hint(ch.remaining, ch.kind), reply_markup=kb.upsell_kb())
        return
    every = ctx.settings.ad_every
    if ch.kind is Kind.CHAT and every > 0 and (user.total_chat + 1) % every == 0:
        ad = await ctx.kv.get(AD_TEXT)
        if ad:
            try:
                await bot.send_message(chat_id, texts.ad_block(ad))
            except TelegramBadRequest:
                log.warning("Ad text has invalid HTML")


async def send_markdown(bot: Bot, chat_id: int, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    chunks = split_text(text)
    for i, chunk in enumerate(chunks):
        markup = reply_markup if i == len(chunks) - 1 else None
        try:
            await bot.send_message(chat_id, md_to_html(chunk), reply_markup=markup)
        except TelegramBadRequest:
            await bot.send_message(chat_id, chunk, parse_mode=None, reply_markup=markup)


# ---------- ИИ-чат ----------


async def _push_draft(bot: Bot, chat_id: int, draft_id: int, text: str, ctx: Services) -> None:
    if len(text) > 4000:
        text = text[:3990] + "…"
    try:
        await bot.send_message_draft(chat_id=chat_id, draft_id=draft_id, text=text, parse_mode=None)
    except TelegramBadRequest as e:
        log.info("Draft streaming disabled: %s", e)
        ctx.draft_streaming = False
    except TelegramAPIError:
        pass


async def _generate_answer(bot: Bot, chat_id: int, messages: Messages, ctx: Services) -> str:
    async with ChatActionSender.typing(bot=bot, chat_id=chat_id):
        if not (ctx.settings.llm_stream and ctx.draft_streaming):
            return await ctx.llm.complete(messages)
        draft_id = random.randint(1, 2**31 - 1)
        parts: list[str] = []
        last_push = time.monotonic()
        async with aclosing(ctx.llm.stream(messages)) as stream:
            async for piece in stream:
                parts.append(piece)
                now = time.monotonic()
                if ctx.draft_streaming and now - last_push >= DRAFT_INTERVAL:
                    visible = strip_think("".join(parts))
                    if visible.strip():
                        last_push = now
                        await _push_draft(bot, chat_id, draft_id, visible, ctx)
        return strip_think("".join(parts)).strip()


async def answer_chat(bot: Bot, chat_id: int, user: User, text: str, ctx: Services) -> None:
    if not await _precheck(bot, chat_id, user, ctx):
        return
    ctx.busy.add(user.id)
    try:
        ch = await _charge(bot, chat_id, user, Kind.CHAT, ctx)
        if ch is None:
            return
        limit = ctx.settings.history_premium if ch.premium else ctx.settings.history_free
        async with ctx.db.session() as s:
            history = await repo.get_history(s, user.id, limit)
        messages: Messages = [
            {"role": "system", "content": ctx.settings.system_prompt},
            *history,
            {"role": "user", "content": text[:MAX_INPUT]},
        ]
        try:
            answer = await _generate_answer(bot, chat_id, messages, ctx)
        except Exception:
            log.exception("LLM failed for user %s", user.id)
            answer = ""
        if not answer:
            await _refund(ctx, user, ch)
            await bot.send_message(chat_id, texts.LLM_ERROR)
            return
        async with ctx.db.begin() as s:
            await repo.save_dialog(s, user.id, text[:MAX_INPUT], answer)
            await billing.record_usage(s, user.id, ch)
        await send_markdown(bot, chat_id, answer)
        await _after_success(bot, chat_id, user, ch, ctx)
    finally:
        ctx.busy.discard(user.id)


# ---------- картинки ----------


async def generate_image(bot: Bot, chat_id: int, user: User, prompt: str, ctx: Services) -> None:
    prompt = prompt.strip()[:1000]
    if not is_prompt_allowed(prompt):
        await bot.send_message(chat_id, texts.PROMPT_FORBIDDEN)
        return
    if not await _precheck(bot, chat_id, user, ctx):
        return
    ctx.busy.add(user.id)
    try:
        ch = await _charge(bot, chat_id, user, Kind.IMAGE, ctx)
        if ch is None:
            return
        status = await bot.send_message(chat_id, texts.image_queued(ctx.gen.load, ch.premium))

        async def fail(text: str) -> None:
            await _refund(ctx, user, ch)
            try:
                await status.edit_text(text)
            except TelegramAPIError:
                await bot.send_message(chat_id, text)

        try:
            english = prompt
            if ctx.settings.image_translate and has_cyrillic(prompt):
                english = await to_image_prompt(ctx.llm, prompt)
                if not is_prompt_allowed(english):
                    await fail(texts.PROMPT_FORBIDDEN)
                    return
            req = build_request(ctx.settings, english, user.image_style, user.image_ratio)
            priority = PRIORITY_PREMIUM if ch.premium else PRIORITY_FREE
            image = await ctx.gen.submit(lambda: ctx.images.generate(req), priority)
        except Exception:
            log.exception("Image generation failed for user %s", user.id)
            await fail(texts.IMAGE_ERROR)
            return

        token = ctx.prompts.put(user.id, prompt)
        me = await bot.me()
        caption = texts.image_caption(prompt, me.username)
        markup = kb.image_result_kb(token)
        try:
            await bot.send_photo(chat_id, BufferedInputFile(image, "image.png"), caption=caption, reply_markup=markup)
        except TelegramBadRequest:
            try:
                await bot.send_document(
                    chat_id, BufferedInputFile(image, "image.png"), caption=caption, reply_markup=markup
                )
            except TelegramAPIError:
                log.exception("Can't deliver image to %s", user.id)
                await fail(texts.IMAGE_ERROR)
                return
        try:
            await status.delete()
        except TelegramAPIError:
            pass
        async with ctx.db.begin() as s:
            await billing.record_usage(s, user.id, ch)
        await _after_success(bot, chat_id, user, ch, ctx)
    finally:
        ctx.busy.discard(user.id)


# ---------- обработчики ----------


@router.message(Command("img", "image", "draw"))
async def cmd_img(message: Message, command: CommandObject, user: User, ctx: Services, bot: Bot) -> None:
    prompt = (command.args or "").strip()
    if not prompt:
        async with ctx.db.begin() as s:
            await repo.set_fields(s, user.id, mode="image")
        await message.answer(texts.EMPTY_PROMPT)
        return
    await generate_image(bot, message.chat.id, user, prompt, ctx)


@router.callback_query(kb.RegenCb.filter())
async def cb_regenerate(callback: CallbackQuery, callback_data: kb.RegenCb, user: User, ctx: Services, bot: Bot) -> None:
    prompt = ctx.prompts.get(callback_data.token, user.id)
    if prompt is None:
        await callback.answer(texts.REGEN_EXPIRED, show_alert=True)
        return
    await callback.answer("🎨")
    await generate_image(bot, callback.message.chat.id, user, prompt, ctx)  # type: ignore[union-attr]


@router.message(F.text & ~F.text.startswith("/"))
async def on_text(message: Message, user: User, ctx: Services, bot: Bot) -> None:
    text = (message.text or "").strip()
    if not text:
        return
    if user.mode == "image":
        await generate_image(bot, message.chat.id, user, text, ctx)
    else:
        await answer_chat(bot, message.chat.id, user, text, ctx)


@router.message(F.text.startswith("/"))
async def on_unknown_command(message: Message) -> None:
    await message.answer("Не знаю такой команды 🤔 Список команд — /help")


@router.message(F.photo | F.voice | F.video | F.document | F.sticker | F.audio | F.video_note | F.animation)
async def on_other_content(message: Message) -> None:
    await message.answer(texts.ONLY_TEXT)
