from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message
from sqlalchemy import or_, update
from sqlalchemy.exc import IntegrityError

from app import keyboards as kb
from app import texts
from app.context import Services
from app.db import repo
from app.db.models import User
from app.services.growth import bot_link
from app.utils import local_today

router = Router(name="bonus")


async def _show_bonus(message: Message, user: User, ctx: Services) -> None:
    link = await bot_link(message.bot, f"ref_{user.id}")  # type: ignore[arg-type]
    async with ctx.db.session() as s:
        fresh = await repo.get_user(s, user.id)
        referrals = await repo.count_referrals(s, user.id)
    assert fresh is not None
    can_claim = fresh.bonus_date != local_today(ctx.settings.tz) and ctx.settings.daily_bonus > 0
    await message.answer(
        texts.bonus_screen(ctx.settings, link, referrals, fresh.ref_earned, can_claim),
        reply_markup=kb.bonus_kb(link, texts.share_text(ctx.settings), can_claim),
    )


@router.message(Command("bonus", "ref"))
@router.message(F.text == kb.BTN_BONUS)
async def menu_bonus(message: Message, user: User, ctx: Services) -> None:
    await _show_bonus(message, user, ctx)


@router.callback_query(kb.MenuCb.filter(F.action == "bonus"))
async def cb_bonus(callback: CallbackQuery, user: User, ctx: Services) -> None:
    await callback.answer()
    await _show_bonus(callback.message, user, ctx)  # type: ignore[arg-type]


@router.callback_query(kb.MenuCb.filter(F.action == "daily"))
async def cb_daily(callback: CallbackQuery, user: User, ctx: Services) -> None:
    amount = ctx.settings.daily_bonus
    today = local_today(ctx.settings.tz)
    async with ctx.db.begin() as s:
        result = await s.execute(
            update(User)
            .where(User.id == user.id, or_(User.bonus_date.is_(None), User.bonus_date != today))
            .values(bonus_date=today, credits=User.credits + amount)
        )
    if result.rowcount != 1 or amount <= 0:
        await callback.answer(texts.DAILY_ALREADY, show_alert=True)
        return
    await callback.answer(texts.daily_claimed(amount), show_alert=True)


@router.message(Command("promo"))
async def cmd_promo(message: Message, command: CommandObject, user: User, ctx: Services) -> None:
    code = (command.args or "").strip().split()[0] if command.args and command.args.strip() else ""
    if not code:
        await message.answer(texts.PROMO_USAGE)
        return
    try:
        async with ctx.db.begin() as s:
            # при ошибке activate_promo ничего не меняет в базе
            result = await repo.activate_promo(s, code, user.id)
    except IntegrityError:
        result = "used"
    if isinstance(result, str):
        await message.answer(texts.PROMO_ERRORS.get(result, texts.PROMO_ERRORS["not_found"]))
        return
    await message.answer(texts.promo_ok(result.credits, result.premium_days))
