"""Tasks: "subscribe to a channel" (verified) and simple link tasks."""

import logging
from datetime import datetime

from aiogram.exceptions import TelegramAPIError
from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.game import clan_service, player_service
from app.game.errors import GameError
from app.models import Task, User, UserTask

log = logging.getLogger(__name__)

CHANNEL_SUB = "channel_sub"
LINK = "link"


def _active(now: datetime):
    return (
        Task.status == "active",
        or_(Task.expires_at.is_(None), Task.expires_at > now),
        or_(Task.max_completions.is_(None), Task.completions < Task.max_completions),
    )


async def list_tasks(session: AsyncSession, user: User, lang: str, now: datetime) -> list[dict]:
    tasks = (
        (await session.execute(select(Task).where(*_active(now)).order_by(Task.id.desc())))
        .scalars()
        .all()
    )
    done = set(
        (
            await session.execute(select(UserTask.task_id).where(UserTask.user_id == user.id))
        ).scalars()
    )
    return [
        {
            "id": task.id,
            "kind": task.kind,
            "title": task.title_ru if lang == "ru" else task.title_en,
            "url": task.url,
            "reward": task.reward,
            "completed": task.id in done,
        }
        for task in tasks
    ]


async def check_task(session: AsyncSession, user: User, task_id: int, now: datetime) -> int:
    """Verifies and pays a task once. User row must be locked. Returns the reward."""
    if await session.get(UserTask, (user.id, task_id)) is not None:
        raise GameError("task_done", 409)
    task = await session.get(Task, task_id)
    if task is None or task.status != "active":
        raise GameError("task_not_found", 404)
    if task.expires_at is not None and task.expires_at <= now:
        raise GameError("task_not_found", 404)

    if task.kind == CHANNEL_SUB:
        if task.tg_chat_id is None:
            raise GameError("task_not_found", 404)
        try:
            subscribed = await clan_service.is_subscribed(task.tg_chat_id, user.id)
        except TelegramAPIError as exc:
            log.warning("task %s check failed: %s", task.id, exc)
            raise GameError("subscription_check_failed", 503) from exc
        if not subscribed:
            raise GameError("not_subscribed", 403)

    # Count the completion atomically so sponsored packages never overshoot.
    counted = await session.execute(
        update(Task)
        .where(
            Task.id == task.id,
            or_(Task.max_completions.is_(None), Task.completions < Task.max_completions),
        )
        .values(completions=Task.completions + 1)
        .returning(Task.completions, Task.max_completions)
    )
    row = counted.one_or_none()
    if row is None:
        raise GameError("task_not_found", 404)
    completions, max_completions = row
    if max_completions is not None and completions >= max_completions:
        await session.execute(update(Task).where(Task.id == task.id).values(status="done"))

    await session.execute(
        insert(UserTask).values(user_id=user.id, task_id=task.id).on_conflict_do_nothing()
    )
    player_service.credit(user, task.reward)
    return task.reward
