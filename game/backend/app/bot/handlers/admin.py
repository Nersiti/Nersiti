"""Admin commands (Telegram ids listed in ADMIN_IDS)."""

import html
from datetime import date, timedelta

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.filters.callback_data import CallbackData
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app import analytics
from app.config import get_settings
from app.db import get_sessionmaker
from app.game import player_service, season_service, shop_service
from app.game.cards import CARDS_BY_ID
from app.game.errors import GameError
from app.game.tasks_service import CHANNEL_SUB, LINK
from app.i18n import pick_lang, t
from app.models import Clan, DailyCombo, Task, User
from app.notify import enqueue, webapp_button
from app.redis_client import get_redis

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


@router.message(Command("task_add"))
async def cmd_task_add(message: Message, command: CommandObject, bot: Bot) -> None:
    """/task_add @channel <reward> <limit|0> <title...>"""
    lang = pick_lang(message.from_user.language_code if message.from_user else None)
    if not is_admin(message):
        await message.answer(t(lang, "admin.only"))
        return
    parts = (command.args or "").split(maxsplit=3)
    if len(parts) < 4 or not parts[1].isdigit() or not parts[2].isdigit():
        await message.answer(t(lang, "admin.task.usage"))
        return
    channel, reward, max_completions, title = parts[0], int(parts[1]), int(parts[2]), parts[3]
    try:
        chat = await bot.get_chat(channel)
        me = await bot.get_chat_member(chat.id, bot.id)
    except TelegramAPIError:
        await message.answer(t(lang, "admin.task.bot_not_admin"))
        return
    if me.status != "administrator":
        await message.answer(t(lang, "admin.task.bot_not_admin"))
        return
    url = f"https://t.me/{chat.username}" if chat.username else (chat.invite_link or "")
    async with get_sessionmaker()() as session:
        task = Task(
            kind=CHANNEL_SUB,
            title_ru=title[:200],
            title_en=title[:200],
            url=url,
            tg_chat_id=chat.id,
            reward=reward,
            status="active",
            max_completions=max_completions or None,
            completions=0,
        )
        session.add(task)
        await session.commit()
    await message.answer(t(lang, "admin.task.created", id=task.id))


@router.message(Command("task_link"))
async def cmd_task_link(message: Message, command: CommandObject) -> None:
    """/task_link <url> <reward> <title...>"""
    lang = pick_lang(message.from_user.language_code if message.from_user else None)
    if not is_admin(message):
        await message.answer(t(lang, "admin.only"))
        return
    parts = (command.args or "").split(maxsplit=2)
    if len(parts) < 3 or not parts[1].isdigit() or not parts[0].startswith("https://"):
        await message.answer(t(lang, "admin.task.usage"))
        return
    async with get_sessionmaker()() as session:
        task = Task(
            kind=LINK,
            title_ru=parts[2][:200],
            title_en=parts[2][:200],
            url=parts[0],
            reward=int(parts[1]),
            status="active",
            completions=0,
        )
        session.add(task)
        await session.commit()
    await message.answer(t(lang, "admin.task.created", id=task.id))


@router.message(Command("tasks"))
async def cmd_tasks(message: Message) -> None:
    lang = pick_lang(message.from_user.language_code if message.from_user else None)
    if not is_admin(message):
        await message.answer(t(lang, "admin.only"))
        return
    async with get_sessionmaker()() as session:
        tasks = (
            (
                await session.execute(
                    select(Task).where(Task.status.in_(["active", "pending"])).order_by(Task.id)
                )
            )
            .scalars()
            .all()
        )
    if not tasks:
        await message.answer(t(lang, "admin.task.none"))
        return
    lines = [
        f"#{x.id} [{x.status}] {x.title_ru} — {x.completions}/{x.max_completions or '∞'}, "
        f"+{x.reward}"
        for x in tasks
    ]
    await message.answer("\n".join(lines), disable_web_page_preview=True)


@router.message(Command("task_off"))
async def cmd_task_off(message: Message, command: CommandObject) -> None:
    lang = pick_lang(message.from_user.language_code if message.from_user else None)
    if not is_admin(message):
        await message.answer(t(lang, "admin.only"))
        return
    if not (command.args or "").strip().isdigit():
        await message.answer(t(lang, "admin.task.usage"))
        return
    task_id = int(command.args.strip())
    async with get_sessionmaker()() as session:
        task = await session.get(Task, task_id)
        if task is not None:
            task.status = "done"
            await session.commit()
    await message.answer(t(lang, "admin.task.off", id=task_id))


# --- Stats, moderation, broadcast, season, combo, gifts --------------------------------


class AdminCb(CallbackData, prefix="adm"):
    action: str  # "broadcast" | "season_end" | "cancel"


def _confirm_keyboard(action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data=AdminCb(action=action).pack()),
                InlineKeyboardButton(
                    text="✖️ Отмена", callback_data=AdminCb(action="cancel").pack()
                ),
            ]
        ]
    )


@router.message(Command("admin"))
async def cmd_admin_help(message: Message) -> None:
    if not is_admin(message):
        return
    await message.answer(
        "🛠 <b>Команды администратора</b>\n\n"
        "/stats — статистика\n"
        "/suspects — подозрительные игроки\n"
        "/ban &lt;id&gt; · /unban &lt;id&gt; · /ban_clan &lt;id&gt;\n"
        "/broadcast &lt;текст&gt; — рассылка всем\n"
        "/season_end — завершить сезон сейчас\n"
        "/combo_set today|tomorrow|ГГГГ-ММ-ДД c1 c2 c3\n"
        "/gifts · /gift &lt;user_id&gt; &lt;gift_id&gt; [текст]\n"
        "/task_add · /task_link · /tasks · /task_off\n"
        "/refund &lt;charge_id&gt;"
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if not is_admin(message):
        return
    async with get_sessionmaker()() as session:
        data = await analytics.stats(session, player_service.utcnow())
    await message.answer(analytics.format_stats(data))


@router.message(Command("suspects"))
async def cmd_suspects(message: Message) -> None:
    if not is_admin(message):
        return
    async with get_sessionmaker()() as session:
        rows = (
            await session.execute(
                select(User.id, User.first_name, User.username, User.suspicion, User.total_earned)
                .where(User.suspicion > 0, User.banned.is_(False))
                .order_by(User.suspicion.desc())
                .limit(20)
            )
        ).all()
    if not rows:
        await message.answer("Подозрительных игроков нет.")
        return
    lines = [
        f"{r.id} · {html.escape(r.first_name)}"
        + (f" @{r.username}" if r.username else "")
        + f" · флагов {r.suspicion} · заработано {r.total_earned}"
        for r in rows
    ]
    await message.answer("🚨 <b>Подозрительные</b>\n\n" + "\n".join(lines))


async def _set_banned(message: Message, command: CommandObject, banned: bool) -> None:
    if not is_admin(message):
        return
    arg = (command.args or "").strip()
    if not arg.lstrip("-").isdigit():
        await message.answer("Использование: /ban <telegram_id>")
        return
    async with get_sessionmaker()() as session:
        user = await session.get(User, int(arg))
        if user is None:
            await message.answer("Игрок не найден.")
            return
        user.banned = banned
        await session.commit()
    await message.answer(f"Игрок {arg}: {'забанен' if banned else 'разбанен'}.")


@router.message(Command("ban"))
async def cmd_ban(message: Message, command: CommandObject) -> None:
    await _set_banned(message, command, True)


@router.message(Command("unban"))
async def cmd_unban(message: Message, command: CommandObject) -> None:
    await _set_banned(message, command, False)


@router.message(Command("ban_clan"))
async def cmd_ban_clan(message: Message, command: CommandObject) -> None:
    if not is_admin(message):
        return
    arg = (command.args or "").strip()
    if not arg.isdigit():
        await message.answer("Использование: /ban_clan <id клана>")
        return
    async with get_sessionmaker()() as session:
        clan = await session.get(Clan, int(arg))
        if clan is None:
            await message.answer("Клан не найден.")
            return
        clan.banned = True
        await session.commit()
    await message.answer(f"Клан {arg} заблокирован.")


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, command: CommandObject) -> None:
    if not is_admin(message):
        return
    text = (command.args or "").strip()
    if not text:
        await message.answer("Использование: /broadcast <текст сообщения>")
        return
    await get_redis().set(f"broadcast:pending:{message.from_user.id}", text, ex=600)
    await message.answer(
        f"Разослать всем игрокам с включёнными уведомлениями?\n\n{text}",
        reply_markup=_confirm_keyboard("broadcast"),
    )


@router.message(Command("season_end"))
async def cmd_season_end(message: Message) -> None:
    if not is_admin(message):
        return
    await message.answer(
        "Завершить текущий сезон прямо сейчас? Будут выданы награды, карта обнулится.",
        reply_markup=_confirm_keyboard("season_end"),
    )


@router.callback_query(AdminCb.filter())
async def on_admin_confirm(callback: CallbackQuery, callback_data: AdminCb) -> None:
    if callback.from_user.id not in get_settings().admin_id_set:
        await callback.answer("Только для администраторов", show_alert=True)
        return
    if callback.message is not None:
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except TelegramAPIError:
            pass
    if callback_data.action == "cancel":
        await callback.answer("Отменено")
        return

    if callback_data.action == "broadcast":
        text = await get_redis().getdel(f"broadcast:pending:{callback.from_user.id}")
        if not text:
            await callback.answer("Текст устарел, отправь /broadcast заново", show_alert=True)
            return
        queued = await broadcast(text)
        await callback.answer()
        if callback.message is not None:
            await callback.message.answer(f"Рассылка поставлена в очередь: {queued} сообщений.")
        return

    if callback_data.action == "season_end":
        async with get_sessionmaker()() as session:
            now = player_service.utcnow()
            await season_service.ensure_active_season(session, now)
            results = await season_service.end_season(session, now, apply=True, force=True)
            await session.commit()
        await callback.answer()
        if callback.message is not None and results is not None:
            winners = ", ".join(c["title"] for c in results["clans"]) or "—"
            await callback.message.answer(
                f"Сезон {results['season']} завершён. Победители: {html.escape(winners)}"
            )


async def broadcast(text: str, batch: int = 1000) -> int:
    """Queues `text` for every player with notifications on (not subject to the daily cap)."""
    queued = 0
    last_id = 0
    button = webapp_button("🌍 Играть")
    async with get_sessionmaker()() as session:
        while True:
            ids = (
                (
                    await session.execute(
                        select(User.id)
                        .where(
                            User.id > last_id, User.notify_enabled.is_(True), User.banned.is_(False)
                        )
                        .order_by(User.id)
                        .limit(batch)
                    )
                )
                .scalars()
                .all()
            )
            if not ids:
                break
            for uid in ids:
                await enqueue(uid, text, button=button, user_id=uid, capped=False)
            queued += len(ids)
            last_id = ids[-1]
    return queued


@router.message(Command("combo_set"))
async def cmd_combo_set(message: Message, command: CommandObject) -> None:
    if not is_admin(message):
        return
    parts = (command.args or "").split()
    if len(parts) != 4:
        await message.answer("Использование: /combo_set today|tomorrow|ГГГГ-ММ-ДД c1 c2 c3")
        return
    today = player_service.utcnow().date()
    try:
        if parts[0] == "today":
            day = today
        elif parts[0] == "tomorrow":
            day = today + timedelta(days=1)
        else:
            day = date.fromisoformat(parts[0])
    except ValueError:
        await message.answer("Неверная дата.")
        return
    cards = parts[1:]
    unknown = [c for c in cards if c not in CARDS_BY_ID]
    if unknown or len(set(cards)) != 3:
        await message.answer(
            "Нужно 3 разные карточки из: "
            + ", ".join(CARDS_BY_ID)
            + (f"\nНеизвестные: {unknown}" if unknown else "")
        )
        return
    async with get_sessionmaker()() as session:
        await session.execute(
            pg_insert(DailyCombo)
            .values(day=day, card_ids=cards)
            .on_conflict_do_update(index_elements=[DailyCombo.day], set_={"card_ids": cards})
        )
        await session.commit()
    await message.answer(f"Комбо на {day}: {', '.join(cards)}")


@router.message(Command("gifts"))
async def cmd_gifts(message: Message, bot: Bot) -> None:
    if not is_admin(message):
        return
    try:
        gifts = await bot.get_available_gifts()
    except TelegramAPIError as exc:
        await message.answer(f"Ошибка: {exc}")
        return
    lines = [f"{g.id} — {g.star_count} ⭐ {g.sticker.emoji or ''}" for g in gifts.gifts[:30]]
    await message.answer("🎁 Доступные подарки:\n\n" + ("\n".join(lines) or "—"))


@router.message(Command("gift"))
async def cmd_gift(message: Message, command: CommandObject, bot: Bot) -> None:
    if not is_admin(message):
        return
    parts = (command.args or "").split(maxsplit=2)
    if len(parts) < 2 or not parts[0].isdigit():
        await message.answer("Использование: /gift <user_id> <gift_id> [текст]")
        return
    try:
        await bot.send_gift(
            gift_id=parts[1], user_id=int(parts[0]), text=parts[2][:128] if len(parts) > 2 else None
        )
    except TelegramAPIError as exc:
        await message.answer(f"Не удалось отправить подарок: {exc}")
        return
    await message.answer("Подарок отправлен 🎁")
