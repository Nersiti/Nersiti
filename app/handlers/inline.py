"""Virality: cards in any chat via @bot word, plus commands in groups."""

from __future__ import annotations

from aiogram import Bot, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultCachedPhoto,
    InlineQueryResultsButton,
    InputTextMessageContent,
    Message,
)
from sqlalchemy import select

from app import keyboards as kb
from app import texts
from app.context import Services
from app.db.models import User
from app.game.service import public_name
from app.game.words import display_form, is_reserved, normalize
from app.handlers.game import top_text
from app.services.growth import bot_link
from app.utils import esc

router = Router(name="inline")
group_router = Router(name="group")
group_router.message.filter(lambda m: m.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP))


@router.inline_query()
async def on_inline(query: InlineQuery, ctx: Services, bot: Bot) -> None:
    raw = query.query.strip()
    word = normalize(raw) if raw else ""
    cards = await ctx.game.search(word or "", limit=10) if word is not None else []

    async with ctx.db.session() as s:
        owners = {u.id: u for u in (await s.scalars(select(User).where(User.id.in_([c.owner_id for c in cards])))).all()}

    results: list = []
    for card in cards:
        link = await bot_link(bot, f"c_{card.id}")
        results.append(
            InlineQueryResultCachedPhoto(
                id=f"c{card.id}",
                photo_file_id=card.file_id or "",
                caption=texts.card_caption(card, owners.get(card.owner_id), ctx.settings),
                reply_markup=kb.url_kb("⚔️ Сразиться или захватить", link),
            )
        )
    if word and not any(c.word == word for c in cards) and not is_reserved(word):
        display = display_form(raw)
        link = await bot_link(bot, "src_inline")
        results.append(
            InlineQueryResultArticle(
                id=f"free{abs(hash(word)) % 10**12}",
                title=f"«{display}» — никому не принадлежит!",
                description="Захвати это слово первым — навсегда",
                input_message_content=InputTextMessageContent(
                    message_text=f"✨ Слово <b>«{esc(display)}»</b> ещё ничьё! Кто первый захватит — владеет навсегда 👇"
                ),
                reply_markup=kb.url_kb("✒️ Захватить", link),
            )
        )
    await query.answer(
        results,
        cache_time=10,
        is_personal=False,
        button=InlineQueryResultsButton(text="✒️ Захватить своё слово", start_parameter="inline"),
    )


@group_router.message(Command("card", "word"))
async def group_card(message: Message, command: CommandObject, ctx: Services, bot: Bot) -> None:
    word = normalize(command.args or "")
    if not word:
        await message.reply("Напиши так: <code>/card слово</code>")
        return
    found = await ctx.game.lookup(word)
    link = await bot_link(bot, f"c_{found.card.id}" if found.card else "src_group")
    if found.card is None:
        await message.reply(
            f"✨ Слово «{esc(display_form(command.args or ''))}» ещё ничьё!",
            reply_markup=kb.url_kb("✒️ Захватить первым", link),
        )
        return
    async with ctx.db.session() as s:
        owner = await s.get(User, found.card.owner_id)
    caption = texts.card_caption(found.card, owner, ctx.settings)
    markup = kb.url_kb(f"⚔️ Отобрать у {public_name(owner)}", link)
    if found.card.file_id:
        await message.reply_photo(found.card.file_id, caption=caption, reply_markup=markup)
    else:
        await message.reply(caption, reply_markup=markup)


@group_router.message(Command("top"))
async def group_top(message: Message, ctx: Services, bot: Bot) -> None:
    link = await bot_link(bot, "src_group")
    await message.reply(await top_text(ctx), reply_markup=kb.url_kb("✒️ Захватить своё слово", link))


@group_router.message(Command("start", "help"))
async def group_start(message: Message, bot: Bot) -> None:
    link = await bot_link(bot, "src_group")
    await message.reply(
        "👑 <b>Хозяин Слова</b> — игра, где можно навсегда завладеть любым словом.\n\n"
        "В чате работают <code>/card слово</code> (кто владеет словом) и <code>/top</code>.\n"
        "Играть — в личке с ботом 👇",
        reply_markup=kb.url_kb("✒️ Захватить своё слово", link),
    )
