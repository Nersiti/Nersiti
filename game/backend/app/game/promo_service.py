"""Self-serve advertising: channel admins buy "subscribe to my channel" tasks for Stars."""

import json
from datetime import datetime

from aiogram import Bot
from aiogram.types import SuccessfulPayment
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.game import economy
from app.game.errors import GameError
from app.game.tasks_service import CHANNEL_SUB
from app.models import Payment, Task
from app.redis_client import get_redis

PREFIX = "promo"
SELECTION_TTL_SECONDS = 24 * 3600


def build_payload(user_id: int, chat_id: int, package_idx: int) -> str:
    return f"{PREFIX}|{user_id}|{chat_id}:{package_idx}"


def is_promo_payload(payload: str) -> bool:
    return payload.startswith(PREFIX + "|")


def parse_payload(payload: str) -> tuple[int, int, int]:
    try:
        prefix, user_id, rest = payload.split("|")
        chat_id, idx = rest.split(":")
        if prefix != PREFIX:
            raise ValueError
        package(int(idx))
        return int(user_id), int(chat_id), int(idx)
    except (ValueError, IndexError) as exc:
        raise GameError("bad_payload") from exc


def package(idx: int) -> tuple[int, int]:
    """(subscribers, stars)"""
    if not 0 <= idx < len(economy.PROMO_PACKAGES):
        raise IndexError(idx)
    return economy.PROMO_PACKAGES[idx]


async def save_selection(user_id: int, chat_id: int, title: str, url: str) -> None:
    data = json.dumps({"chat_id": chat_id, "title": title, "url": url}, ensure_ascii=False)
    await get_redis().set(f"promo:sel:{user_id}", data, ex=SELECTION_TTL_SECONDS)


async def get_selection(user_id: int) -> dict | None:
    raw = await get_redis().get(f"promo:sel:{user_id}")
    return json.loads(raw) if raw else None


async def process_payment(
    session: AsyncSession, payer_id: int, payment: SuccessfulPayment, now: datetime
) -> Task | None:
    """Records the payment and creates a pending task, exactly once per charge id."""
    user_id, chat_id, idx = parse_payload(payment.invoice_payload)
    subs, stars = package(idx)
    inserted = await session.execute(
        insert(Payment)
        .values(
            user_id=payer_id,
            item_id="promo_task",
            stars=payment.total_amount,
            telegram_payment_charge_id=payment.telegram_payment_charge_id,
            payload=payment.invoice_payload,
            status="paid",
            created_at=now,
        )
        .on_conflict_do_nothing(index_elements=[Payment.telegram_payment_charge_id])
        .returning(Payment.id)
    )
    if inserted.scalar_one_or_none() is None:
        return None
    selection = await get_selection(user_id) or {}
    title = selection.get("title") or str(chat_id)
    url = selection.get("url") or ""
    task = Task(
        kind=CHANNEL_SUB,
        title_ru=f"Подпишись на «{title}»"[:200],
        title_en=f"Subscribe to «{title}»"[:200],
        url=url,
        tg_chat_id=chat_id,
        reward=economy.PROMO_TASK_REWARD,
        status="pending",
        max_completions=subs,
        completions=0,
        sponsor_user_id=payer_id,
        stars_paid=payment.total_amount,
        payment_charge_id=payment.telegram_payment_charge_id,
        created_at=now,
    )
    session.add(task)
    await session.flush()
    return task


async def approve(session: AsyncSession, task_id: int) -> Task:
    task = await session.get(Task, task_id, with_for_update=True)
    if task is None or task.status != "pending":
        raise GameError("task_not_found", 404)
    task.status = "active"
    return task


async def reject(session: AsyncSession, bot: Bot, task_id: int) -> Task:
    task = await session.get(Task, task_id, with_for_update=True)
    if task is None or task.status != "pending":
        raise GameError("task_not_found", 404)
    if task.sponsor_user_id and task.payment_charge_id:
        await bot.refund_star_payment(
            user_id=task.sponsor_user_id, telegram_payment_charge_id=task.payment_charge_id
        )
        await session.execute(
            update(Payment)
            .where(Payment.telegram_payment_charge_id == task.payment_charge_id)
            .values(status="refunded")
        )
    task.status = "rejected"
    return task
