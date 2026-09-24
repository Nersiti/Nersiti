from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import BaseFilter, Command, CommandObject
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app import keyboards as kb
from app import texts
from app.context import Services
from app.db import repo
from app.db.models import User
from app.services.channels import parse_channels
from app.services.growth import bot_link, post_showcase, run_broadcast
from app.services.kv import AD_TEXT, REQUIRED_CHANNELS
from app.utils import credits_word, esc, fmt_dt, sanitize_tag, utcnow

log = logging.getLogger(__name__)


class IsAdmin(BaseFilter):
    async def __call__(self, event: TelegramObject, ctx: Services, **_: Any) -> bool:
        user = getattr(event, "from_user", None)
        return bool(user and ctx.settings.is_admin(user.id))


router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


def _args(command: CommandObject) -> list[str]:
    return (command.args or "").split()


async def _target(ctx: Services, query: str) -> User | None:
    async with ctx.db.session() as s:
        return await repo.find_user(s, query)


def _spawn(ctx: Services, coro: Any, name: str) -> None:
    task = asyncio.create_task(coro, name=name)
    ctx.tasks.append(task)
    task.add_done_callback(lambda t: ctx.tasks.remove(t) if t in ctx.tasks else None)


@router.message(Command("admin", "stats"))
async def cmd_stats(message: Message, ctx: Services) -> None:
    async with ctx.db.session() as s:
        stats = await repo.collect_stats(s, ctx.settings.tz)
    await message.answer(texts.admin_stats(stats) + texts.ADMIN_HELP)


@router.message(Command("sources"))
async def cmd_sources(message: Message, ctx: Services) -> None:
    async with ctx.db.session() as s:
        rows = await repo.source_stats(s)
    await message.answer(texts.admin_sources(rows))


@router.message(Command("link"))
async def cmd_link(message: Message, command: CommandObject, bot: Bot) -> None:
    tag = sanitize_tag(command.args or "")
    if not tag:
        await message.answer("Использование: <code>/link vk_post1</code> (латиница, цифры, _ и -)")
        return
    link = await bot_link(bot, f"src_{tag}")
    await message.answer(f"🔗 Ссылка для источника <b>{esc(tag)}</b>:\n<code>{link}</code>\n\nСтатистика — /sources")


@router.message(Command("user"))
async def cmd_user(message: Message, command: CommandObject, ctx: Services) -> None:
    args = _args(command)
    if not args:
        await message.answer("Использование: <code>/user 123456</code> или <code>/user @username</code>")
        return
    target = await _target(ctx, args[0])
    if target is None:
        await message.answer("Пользователь не найден.")
        return
    async with ctx.db.session() as s:
        referrals = await repo.count_referrals(s, target.id)
        payments = await repo.user_payments_summary(s, target.id)
    await message.answer(texts.admin_user(target, ctx.settings, referrals, payments))


@router.message(Command("give"))
async def cmd_give(message: Message, command: CommandObject, ctx: Services, bot: Bot) -> None:
    args = _args(command)
    if len(args) != 2 or not args[1].lstrip("-").isdigit():
        await message.answer("Использование: <code>/give 123456 100</code>")
        return
    target = await _target(ctx, args[0])
    if target is None:
        await message.answer("Пользователь не найден.")
        return
    amount = int(args[1])
    async with ctx.db.begin() as s:
        await repo.add_credits(s, target.id, amount)
    await message.answer(f"✅ {target.id}: {'+' if amount > 0 else ''}{amount} кредитов")
    if amount > 0:
        try:
            await bot.send_message(target.id, f"🎁 Тебе начислено <b>{credits_word(amount)}</b>!")
        except TelegramAPIError:
            pass


@router.message(Command("premium"))
async def cmd_premium(message: Message, command: CommandObject, ctx: Services, bot: Bot) -> None:
    args = _args(command)
    if len(args) != 2 or not args[1].isdigit():
        await message.answer("Использование: <code>/premium 123456 30</code>")
        return
    target = await _target(ctx, args[0])
    if target is None:
        await message.answer("Пользователь не найден.")
        return
    async with ctx.db.begin() as s:
        until = await repo.extend_premium(s, target.id, int(args[1]), utcnow())
    await message.answer(f"✅ Premium для {target.id} до {fmt_dt(until, ctx.settings.tz)}")
    try:
        await bot.send_message(target.id, f"💎 Тебе подарен Premium до <b>{fmt_dt(until, ctx.settings.tz)}</b>!")
    except TelegramAPIError:
        pass


@router.message(Command("ban", "unban"))
async def cmd_ban(message: Message, command: CommandObject, ctx: Services) -> None:
    args = _args(command)
    if not args:
        await message.answer("Использование: <code>/ban 123456</code>")
        return
    target = await _target(ctx, args[0])
    if target is None:
        await message.answer("Пользователь не найден.")
        return
    banned = (command.command or "") == "ban"
    async with ctx.db.begin() as s:
        await repo.set_fields(s, target.id, is_banned=banned)
    await message.answer(f"{'🚫 Забанен' if banned else '✅ Разбанен'}: {target.id}")


@router.message(Command("promo_new"))
async def cmd_promo_new(message: Message, command: CommandObject, ctx: Services) -> None:
    args = _args(command)
    usage = "Использование: <code>/promo_new КОД кредиты [активаций=100] [дней_premium=0] [дней_жизни=0]</code>"
    if len(args) < 2 or not all(a.isdigit() for a in args[1:5]):
        await message.answer(usage)
        return
    code = sanitize_tag(args[0]).upper()
    credits = int(args[1])
    max_uses = int(args[2]) if len(args) > 2 else 100
    premium_days = int(args[3]) if len(args) > 3 else 0
    lifetime = int(args[4]) if len(args) > 4 else 0
    expires = utcnow() + timedelta(days=lifetime) if lifetime else None
    try:
        async with ctx.db.begin() as s:
            await repo.create_promo(s, code, credits, max_uses, premium_days, expires)
    except IntegrityError:
        await message.answer("Такой промокод уже существует.")
        return
    await message.answer(
        f"✅ Промокод <code>{code}</code>: {credits} кредитов, Premium {premium_days} дн., "
        f"активаций {max_uses or '∞'}, до {fmt_dt(expires, ctx.settings.tz)}"
    )


@router.message(Command("promos"))
async def cmd_promos(message: Message, ctx: Services) -> None:
    async with ctx.db.session() as s:
        promos = await repo.list_promos(s)
    if not promos:
        await message.answer("Промокодов пока нет. Создать: /promo_new")
        return
    lines = [
        f"<code>{p.code}</code> — {p.credits} кр., {p.premium_days} дн. · {p.used}/{p.max_uses or '∞'}"
        for p in promos
    ]
    await message.answer("🎟 <b>Промокоды</b>\n\n" + "\n".join(lines))


@router.message(Command("refund"))
async def cmd_refund(message: Message, command: CommandObject, ctx: Services, bot: Bot) -> None:
    args = _args(command)
    if not args:
        await message.answer("Использование: <code>/refund charge_id</code> (есть в уведомлении об оплате)")
        return
    try:
        result = await ctx.payments.refund_stars(bot, args[0])
    except TelegramAPIError as e:
        result = f"Ошибка Telegram: {esc(str(e))}"
    await message.answer(result)


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, ctx: Services) -> None:
    source = message.reply_to_message
    if source is None:
        await message.answer("Ответь командой /broadcast на сообщение, которое нужно разослать всем.")
        return
    async with ctx.db.session() as s:
        count = await s.scalar(
            select(func.count()).select_from(User).where(User.is_blocked.is_(False), User.is_banned.is_(False))
        )
    ctx.pending_broadcasts[message.from_user.id] = (source.chat.id, source.message_id)  # type: ignore[union-attr]
    await message.answer(
        f"Разослать это сообщение {count} пользователям?", reply_markup=kb.broadcast_confirm_kb(int(count or 0))
    )


@router.callback_query(kb.BroadcastCb.filter())
async def cb_broadcast(callback: CallbackQuery, callback_data: kb.BroadcastCb, ctx: Services, bot: Bot) -> None:
    pending = ctx.pending_broadcasts.pop(callback.from_user.id, None)
    if callback_data.action != "go" or pending is None:
        await callback.answer("Отменено")
        await callback.message.edit_text("❌ Рассылка отменена.")  # type: ignore[union-attr]
        return
    await callback.answer()
    await callback.message.edit_text("📤 Рассылка запущена, по завершении пришлю отчёт.")  # type: ignore[union-attr]
    _spawn(ctx, run_broadcast(bot, ctx, callback.from_user.id, *pending), "broadcast")


@router.message(Command("setad"))
async def cmd_setad(message: Message, command: CommandObject, ctx: Services) -> None:
    if not command.args:
        current = await ctx.kv.get(AD_TEXT)
        await message.answer(
            "Реклама показывается бесплатным пользователям каждые "
            f"{ctx.settings.ad_every} ответов.\n\nТекущая: {current or 'нет'}\n\n"
            "Установить: <code>/setad текст с &lt;b&gt;HTML&lt;/b&gt;</code>\nВыключить: <code>/setad off</code>"
        )
        return
    if command.args.strip().lower() == "off":
        await ctx.kv.set(AD_TEXT, None)
        await message.answer("✅ Реклама выключена.")
        return
    html_text = (message.html_text or "").split(maxsplit=1)
    ad = html_text[1] if len(html_text) > 1 else command.args
    await ctx.kv.set(AD_TEXT, ad)
    await message.answer("✅ Реклама сохранена. Так её увидят пользователи:")
    await message.answer(texts.ad_block(ad))


@router.message(Command("channels"))
async def cmd_channels(message: Message, command: CommandObject, ctx: Services) -> None:
    args = (command.args or "").strip()
    if args.lower() == "off":
        await ctx.kv.set(REQUIRED_CHANNELS, "")
    elif args.lower() == "reset":
        await ctx.kv.set(REQUIRED_CHANNELS, None)
    elif args.lower().startswith("set "):
        entries = [x.strip() for x in args[4:].split(",") if x.strip()]
        if not parse_channels(entries):
            await message.answer("Не удалось разобрать каналы. Формат: <code>@channel</code> или <code>-100id|ссылка</code>")
            return
        await ctx.kv.set(REQUIRED_CHANNELS, ",".join(entries))
    elif args:
        await message.answer("Использование: <code>/channels set @a,@b</code> | <code>off</code> | <code>reset</code>")
        return
    channels = await ctx.gate.channels()
    listed = "\n".join(f"• {esc(str(c.chat))} — {esc(c.url)}" for c in channels) or "нет"
    await message.answer(
        f"📢 <b>Обязательная подписка</b>\n\n{listed}\n\n"
        "Бот должен быть администратором каждого канала, иначе проверка пропускается."
    )


@router.message(Command("showcase"))
async def cmd_showcase(message: Message, ctx: Services, bot: Bot) -> None:
    if not ctx.settings.showcase_channel:
        await message.answer("Канал-витрина не настроен (SHOWCASE_CHANNEL в .env).")
        return

    async def job() -> None:
        try:
            ok = await post_showcase(bot, ctx)
            await bot.send_message(message.chat.id, "✅ Пост опубликован." if ok else "Нет промптов для витрины.")
        except Exception as e:  # noqa: BLE001
            log.exception("Showcase failed")
            await bot.send_message(message.chat.id, f"❌ Ошибка: {esc(repr(e))[:500]}")

    _spawn(ctx, job(), "showcase-now")
    await message.answer("🎨 Генерирую пост для витрины…")
