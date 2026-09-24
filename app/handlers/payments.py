from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery

from app import keyboards as kb
from app import texts
from app.context import Services
from app.db import repo
from app.db.models import User
from app.products import Product, get_product
from app.services.payments.service import STARS, TG_RUB, YOOKASSA

log = logging.getLogger(__name__)
router = Router(name="payments")


async def _show_shop(message: Message, ctx: Services) -> None:
    methods = ctx.payments.methods()
    await message.answer(texts.shop(ctx.settings, methods), reply_markup=kb.shop_kb(methods))


@router.message(Command("buy", "shop"))
@router.message(F.text == kb.BTN_SHOP)
async def menu_buy(message: Message, ctx: Services) -> None:
    await _show_shop(message, ctx)


@router.callback_query(kb.MenuCb.filter(F.action == "shop"))
async def cb_buy(callback: CallbackQuery, ctx: Services) -> None:
    await callback.answer()
    await _show_shop(callback.message, ctx)  # type: ignore[arg-type]


async def _start_payment(bot: Bot, chat_id: int, user: User, product: Product, method: str, ctx: Services) -> None:
    if method == STARS:
        link = await ctx.payments.send_stars_invoice(bot, chat_id, user.id, product)
        if link:
            await bot.send_message(
                chat_id,
                texts.subscription_offer(product),
                reply_markup=kb.url_kb(f"⭐ Оформить за {product.stars} ⭐ / мес", link),
            )
    elif method == TG_RUB:
        await ctx.payments.send_rub_invoice(bot, chat_id, user.id, product)
    elif method == YOOKASSA:
        payment_id, url = await ctx.payments.create_yookassa_payment(user.id, product)
        await bot.send_message(chat_id, texts.yookassa_link(product), reply_markup=kb.yookassa_kb(url, payment_id))


@router.callback_query(kb.BuyCb.filter())
async def cb_product(callback: CallbackQuery, callback_data: kb.BuyCb, user: User, ctx: Services, bot: Bot) -> None:
    product = get_product(callback_data.code)
    methods = ctx.payments.methods()
    if product is None or not methods:
        await callback.answer(texts.PAYMENT_UNAVAILABLE, show_alert=True)
        return
    await callback.answer()
    chat_id = callback.message.chat.id  # type: ignore[union-attr]
    if len(methods) == 1:
        await _pay(bot, chat_id, user, product, methods[0], ctx)
        return
    await bot.send_message(chat_id, texts.choose_method(product), reply_markup=kb.methods_kb(product, methods))


@router.callback_query(kb.PayCb.filter())
async def cb_pay(callback: CallbackQuery, callback_data: kb.PayCb, user: User, ctx: Services, bot: Bot) -> None:
    product = get_product(callback_data.code)
    if product is None or callback_data.method not in ctx.payments.methods():
        await callback.answer(texts.PAYMENT_UNAVAILABLE, show_alert=True)
        return
    await callback.answer()
    await _pay(bot, callback.message.chat.id, user, product, callback_data.method, ctx)  # type: ignore[union-attr]


async def _pay(bot: Bot, chat_id: int, user: User, product: Product, method: str, ctx: Services) -> None:
    try:
        await _start_payment(bot, chat_id, user, product, method, ctx)
    except Exception:
        log.exception("Failed to start %s payment for %s", method, user.id)
        await bot.send_message(chat_id, texts.PAYMENT_UNAVAILABLE)


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery, user: User, ctx: Services) -> None:
    valid = ctx.payments.validate_checkout(query.invoice_payload, query.currency, query.total_amount)
    if valid and not user.is_banned:
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message=texts.PRECHECKOUT_FAIL)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message, ctx: Services, bot: Bot) -> None:
    sp = message.successful_payment
    assert sp is not None and message.from_user is not None
    fulfillment = await ctx.payments.process_telegram_payment(message.from_user.id, sp)
    if fulfillment is None:
        # дубликат уже обработан; неизвестный товар — просим написать в поддержку
        if get_product(sp.invoice_payload.partition(":")[0]) is None:
            await message.answer(texts.PAYMENT_UNKNOWN_PRODUCT)
        return
    await ctx.payments.notify(bot, fulfillment)


@router.callback_query(kb.CheckCb.filter())
async def cb_check_payment(callback: CallbackQuery, callback_data: kb.CheckCb, user: User, ctx: Services, bot: Bot) -> None:
    try:
        status, fulfillment = await ctx.payments.check_yookassa_payment(callback_data.pid)
    except Exception:
        log.exception("YooKassa check failed")
        await callback.answer(texts.PAYMENT_PENDING, show_alert=True)
        return
    if fulfillment:
        await callback.answer("✅")
        await ctx.payments.notify(bot, fulfillment)
    elif status == "succeeded":
        await callback.answer("✅ Этот платёж уже зачислен.", show_alert=True)
    elif status in ("canceled", "expired", "failed", "not_found"):
        await callback.answer(texts.PAYMENT_CANCELED, show_alert=True)
    else:
        await callback.answer(texts.PAYMENT_PENDING, show_alert=True)


@router.callback_query(kb.SubCb.filter())
async def cb_subscription(callback: CallbackQuery, callback_data: kb.SubCb, user: User, ctx: Services, bot: Bot) -> None:
    if not user.sub_charge_id:
        await callback.answer(texts.SUB_ERROR, show_alert=True)
        return
    cancel = callback_data.action == "cancel"
    try:
        await bot.edit_user_star_subscription(
            user_id=user.id, telegram_payment_charge_id=user.sub_charge_id, is_canceled=cancel
        )
    except TelegramAPIError as e:
        log.warning("edit_user_star_subscription failed for %s: %s", user.id, e)
        await callback.answer(texts.SUB_ERROR, show_alert=True)
        return
    async with ctx.db.begin() as s:
        await repo.set_fields(s, user.id, sub_canceled=cancel)
    await callback.answer(texts.SUB_CANCELED if cancel else texts.SUB_RESUMED, show_alert=True)
