"""Telegram Stars payments: pre-checkout validation and granting."""

import logging

from aiogram import F, Router
from aiogram.types import Message, PreCheckoutQuery

from app.bot.handlers.promote import notify_admins
from app.db import get_sessionmaker
from app.game import player_service, promo_service, shop_service
from app.game.errors import GameError
from app.i18n import pick_lang, t
from app.models import User

log = logging.getLogger(__name__)
router = Router()


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery) -> None:
    """Must be answered within 10 seconds."""
    lang = pick_lang(query.from_user.language_code)
    if promo_service.is_promo_payload(query.invoice_payload):
        try:
            user_id, _chat_id, idx = promo_service.parse_payload(query.invoice_payload)
            _subs, stars = promo_service.package(idx)
            ok = (
                user_id == query.from_user.id
                and query.currency == "XTR"
                and query.total_amount == stars
            )
        except GameError:
            ok = False
        if ok:
            await query.answer(ok=True)
        else:
            await query.answer(ok=False, error_message=t(lang, "payment.error"))
        return
    try:
        item, user_id, param = shop_service.parse_payload(query.invoice_payload)
        if query.currency != "XTR" or query.total_amount != item.stars:
            raise GameError("price_mismatch")
        if user_id != query.from_user.id:
            raise GameError("wrong_user")
        async with get_sessionmaker()() as session:
            user = await session.get(User, user_id)
            if user is None or user.banned:
                raise GameError("no_user")
            await shop_service.check_purchase(session, user, item, param, player_service.utcnow())
    except GameError as exc:
        log.info("pre_checkout rejected (%s): %s", exc.code, query.invoice_payload)
        await query.answer(ok=False, error_message=t(lang, "payment.error"))
        return
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message) -> None:
    payment = message.successful_payment
    lang = pick_lang(message.from_user.language_code)
    if promo_service.is_promo_payload(payment.invoice_payload):
        async with get_sessionmaker()() as session:
            task = await promo_service.process_payment(
                session, message.from_user.id, payment, player_service.utcnow()
            )
            await session.commit()
        if task is not None:
            await message.answer(t(lang, "promote.paid"))
            await notify_admins(message.bot, task, message.from_user.full_name)
        return
    async with get_sessionmaker()() as session:
        granted, key = await shop_service.process_successful_payment(
            session, message.from_user.id, payment, player_service.utcnow()
        )
        await session.commit()
    if granted and key:
        await message.answer(t(lang, key))
