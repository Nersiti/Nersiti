"""Admin commands (Telegram ids listed in ADMIN_IDS)."""

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import select

from app.config import get_settings
from app.db import get_sessionmaker
from app.game import shop_service
from app.game.errors import GameError
from app.game.tasks_service import CHANNEL_SUB, LINK
from app.i18n import pick_lang, t
from app.models import Task

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
