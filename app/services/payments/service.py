"""Payments: Telegram Stars, rubles via a Telegram provider, and YooKassa directly. Crediting is idempotent."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import LabeledPrice, SuccessfulPayment
from sqlalchemy import case, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import texts
from app.config import Settings
from app.db import repo
from app.db.database import Database
from app.db.models import Payment, User
from app.products import SUBSCRIPTION_PERIOD, Product, get_product, make_payload, parse_payload
from app.services.payments.yookassa import YooKassaClient
from app.utils import from_timestamp, utcnow

log = logging.getLogger(__name__)

STARS = "stars"
TG_RUB = "tg_rub"
YOOKASSA = "yookassa"
PENDING_TTL = timedelta(hours=24)


@dataclass
class Fulfillment:
    user_id: int
    product: Product
    credits: int
    premium_until: datetime | None
    referrer_id: int | None
    referrer_bonus: int
    renewal: bool = False
    amount: int = 0  # звёзды или копейки
    currency: str = ""
    charge_id: str = ""


async def fulfill(
    s: AsyncSession, settings: Settings, user_id: int, product: Product, sub_until: datetime | None = None
) -> Fulfillment:
    now = utcnow()
    if product.credits:
        await repo.add_credits(s, user_id, product.credits)
    until = None
    if product.premium_days:
        until = await repo.extend_premium(s, user_id, product.premium_days, now, at_least=sub_until)

    referrer_id = await s.scalar(select(User.referrer_id).where(User.id == user_id))
    bonus = 0
    if referrer_id and settings.ref_percent > 0:
        bonus = product.ref_value * settings.ref_percent // 100
        if bonus:
            await s.execute(
                update(User)
                .where(User.id == referrer_id)
                .values(credits=User.credits + bonus, ref_earned=User.ref_earned + bonus)
            )
    return Fulfillment(user_id, product, product.credits, until, referrer_id, bonus)


class PaymentService:
    def __init__(self, db: Database, settings: Settings, yookassa: YooKassaClient | None = None) -> None:
        self.db = db
        self.settings = settings
        self.yookassa = yookassa

    def methods(self) -> list[str]:
        result = []
        if self.settings.stars_enabled:
            result.append(STARS)
        if self.settings.rub_via_telegram:
            result.append(TG_RUB)
        if self.yookassa is not None:
            result.append(YOOKASSA)
        return result

    # ---------- выставление счетов ----------

    async def send_stars_invoice(self, bot: Bot, chat_id: int, user_id: int, product: Product) -> str | None:
        """Send a Stars invoice. For subscriptions, returns an invoice link instead of sending an invoice."""
        prices = [LabeledPrice(label=product.title, amount=product.stars)]
        payload = make_payload(product, user_id)
        if product.subscription:
            return await bot.create_invoice_link(
                title=product.title,
                description=product.description,
                payload=payload,
                currency="XTR",
                prices=prices,
                subscription_period=SUBSCRIPTION_PERIOD,
            )
        await bot.send_invoice(
            chat_id=chat_id,
            title=product.title,
            description=product.description,
            payload=payload,
            currency="XTR",
            prices=prices,
        )
        return None

    async def send_rub_invoice(self, bot: Bot, chat_id: int, user_id: int, product: Product) -> None:
        provider_data = None
        if self.settings.rub_receipt:
            provider_data = json.dumps(
                {
                    "receipt": {
                        "items": [
                            {
                                "description": product.title,
                                "quantity": "1.00",
                                "amount": {"value": f"{product.rub}.00", "currency": "RUB"},
                                "vat_code": self.settings.rub_vat_code,
                                "payment_mode": "full_payment",
                                "payment_subject": "service",
                            }
                        ]
                    }
                },
                ensure_ascii=False,
            )
        await bot.send_invoice(
            chat_id=chat_id,
            title=product.title,
            description=product.description,
            payload=make_payload(product, user_id),
            currency="RUB",
            prices=[LabeledPrice(label=product.title, amount=product.rub * 100)],
            provider_token=self.settings.rub_provider_token.get_secret_value(),
            need_email=self.settings.rub_receipt or None,
            send_email_to_provider=self.settings.rub_receipt or None,
            provider_data=provider_data,
        )

    def validate_checkout(self, payload: str, currency: str, total_amount: int) -> bool:
        parsed = parse_payload(payload)
        product = get_product(parsed[0]) if parsed else None
        if product is None:
            return False
        if currency == "XTR":
            return self.settings.stars_enabled and total_amount == product.stars
        if currency == "RUB":
            return self.settings.rub_via_telegram and total_amount == product.rub * 100
        return False

    # ---------- оплата внутри Telegram (Stars и провайдеры) ----------

    async def process_telegram_payment(self, payer_id: int, sp: SuccessfulPayment) -> Fulfillment | None:
        """Credit the purchase. Returns None for a duplicate or an unknown product."""
        parsed = parse_payload(sp.invoice_payload)
        code = parsed[0] if parsed else sp.invoice_payload[:32]
        product = get_product(code)
        provider = STARS if sp.currency == "XTR" else TG_RUB
        now = utcnow()
        sub_until = from_timestamp(sp.subscription_expiration_date) if sp.subscription_expiration_date else None
        try:
            async with self.db.begin() as s:
                duplicate = await s.scalar(
                    select(Payment.id).where(
                        Payment.provider == provider, Payment.external_id == sp.telegram_payment_charge_id
                    )
                )
                if duplicate:
                    log.info("Duplicate payment %s ignored", sp.telegram_payment_charge_id)
                    return None
                s.add(
                    Payment(
                        user_id=payer_id,
                        provider=provider,
                        product_code=code,
                        amount=sp.total_amount,
                        currency=sp.currency,
                        status="succeeded",
                        external_id=sp.telegram_payment_charge_id,
                        provider_charge_id=sp.provider_payment_charge_id or None,
                        is_recurring=bool(sp.is_recurring),
                        created_at=now,
                        paid_at=now,
                    )
                )
                await s.flush()
                if product is None:
                    log.error("Payment for unknown product %r from %s", code, payer_id)
                    return None

                result = await fulfill(s, self.settings, payer_id, product, sub_until)
                spent = User.stars_spent if provider == STARS else User.rub_spent
                values: dict[object, object] = {spent: spent + sp.total_amount}
                if product.subscription and provider == STARS and (sp.is_first_recurring or not sp.is_recurring):
                    values[User.sub_charge_id] = sp.telegram_payment_charge_id
                    values[User.sub_canceled] = False
                await s.execute(update(User).where(User.id == payer_id).values(values))
                result.renewal = bool(sp.is_recurring and not sp.is_first_recurring)
                result.amount, result.currency = sp.total_amount, sp.currency
                result.charge_id = sp.telegram_payment_charge_id
                return result
        except IntegrityError:
            log.info("Payment %s already processed concurrently", sp.telegram_payment_charge_id)
            return None

    # ---------- ЮKassa напрямую ----------

    async def create_yookassa_payment(self, user_id: int, product: Product) -> tuple[int, str]:
        assert self.yookassa is not None
        async with self.db.begin() as s:
            payment = Payment(
                user_id=user_id,
                provider=YOOKASSA,
                product_code=product.code,
                amount=product.rub * 100,
                currency="RUB",
                status="pending",
                created_at=utcnow(),
            )
            s.add(payment)
            await s.flush()
            payment_id = payment.id
        try:
            data = await self.yookassa.create_payment(
                amount_rub=product.rub,
                description=f"{product.title} (ID {user_id})",
                metadata={"payment_id": payment_id, "user_id": user_id, "product": product.code},
                idempotence_key=f"{payment_id}-{uuid.uuid4().hex}",
            )
        except Exception:
            async with self.db.begin() as s:
                await s.execute(update(Payment).where(Payment.id == payment_id).values(status="failed"))
            raise
        async with self.db.begin() as s:
            await s.execute(update(Payment).where(Payment.id == payment_id).values(external_id=data["id"]))
        return payment_id, data["confirmation"]["confirmation_url"]

    async def check_yookassa_payment(self, payment_id: int) -> tuple[str, Fulfillment | None]:
        async with self.db.session() as s:
            payment = await s.get(Payment, payment_id)
        if payment is None or payment.provider != YOOKASSA or self.yookassa is None:
            return "not_found", None
        if payment.status != "pending" or not payment.external_id:
            return payment.status, None

        info = await self.yookassa.get_payment(payment.external_id)
        status = info.get("status")
        if status == "succeeded" and info.get("paid"):
            amount = info.get("amount") or {}
            paid_kopecks = round(float(amount.get("value", 0)) * 100)
            if paid_kopecks != payment.amount or amount.get("currency") != "RUB":
                log.error("YooKassa amount mismatch for payment %s: %s", payment_id, amount)
                async with self.db.begin() as s:
                    await s.execute(update(Payment).where(Payment.id == payment_id).values(status="mismatch"))
                return "mismatch", None
            product = get_product(payment.product_code)
            async with self.db.begin() as s:
                result = await s.execute(
                    update(Payment)
                    .where(Payment.id == payment_id, Payment.status == "pending")
                    .values(status="succeeded", paid_at=utcnow())
                )
                if result.rowcount != 1 or product is None:
                    return "succeeded", None
                fulfillment = await fulfill(s, self.settings, payment.user_id, product)
                fulfillment.amount, fulfillment.currency = payment.amount, "RUB"
                fulfillment.charge_id = payment.external_id
                await s.execute(
                    update(User)
                    .where(User.id == payment.user_id)
                    .values(rub_spent=User.rub_spent + payment.amount)
                )
            return "succeeded", fulfillment
        if status == "canceled":
            async with self.db.begin() as s:
                await s.execute(
                    update(Payment)
                    .where(Payment.id == payment_id, Payment.status == "pending")
                    .values(status="canceled")
                )
            return "canceled", None
        return "pending", None

    async def poll_yookassa(self, bot: Bot, interval: float = 20.0) -> None:
        """Background task: checks pending YooKassa payments."""
        while True:
            await asyncio.sleep(interval)
            try:
                since = utcnow() - PENDING_TTL
                async with self.db.session() as s:
                    ids = (
                        await s.scalars(
                            select(Payment.id)
                            .where(
                                Payment.provider == YOOKASSA,
                                Payment.status == "pending",
                                Payment.external_id.is_not(None),
                                Payment.created_at >= since,
                            )
                            .order_by(Payment.id.desc())
                            .limit(50)
                        )
                    ).all()
                for payment_id in ids:
                    _, fulfillment = await self.check_yookassa_payment(payment_id)
                    if fulfillment:
                        await self.notify(bot, fulfillment)
                async with self.db.begin() as s:
                    await s.execute(
                        update(Payment)
                        .where(Payment.provider == YOOKASSA, Payment.status == "pending", Payment.created_at < since)
                        .values(status="expired")
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("YooKassa polling failed")

    # ---------- уведомления, возвраты ----------

    async def notify(self, bot: Bot, f: Fulfillment) -> None:
        try:
            await bot.send_message(f.user_id, texts.payment_success(f, self.settings))
        except TelegramAPIError as e:
            log.warning("Can't notify buyer %s: %s", f.user_id, e)
        if f.referrer_id and f.referrer_bonus:
            try:
                await bot.send_message(f.referrer_id, texts.referral_commission(f.referrer_bonus))
            except TelegramAPIError:
                pass
        for admin_id in self.settings.admin_ids:
            try:
                await bot.send_message(admin_id, texts.admin_payment(f))
            except TelegramAPIError:
                pass

    async def refund_stars(self, bot: Bot, charge_id: str) -> str:
        async with self.db.session() as s:
            payment = await s.scalar(
                select(Payment).where(Payment.provider == STARS, Payment.external_id == charge_id)
            )
        if payment is None:
            return "Платёж не найден."
        if payment.status == "refunded":
            return "Этот платёж уже возвращён."
        await bot.refund_star_payment(user_id=payment.user_id, telegram_payment_charge_id=charge_id)

        product = get_product(payment.product_code)
        now = utcnow()
        async with self.db.begin() as s:
            await s.execute(update(Payment).where(Payment.id == payment.id).values(status="refunded"))
            spent = User.stars_spent - payment.amount
            await s.execute(
                update(User)
                .where(User.id == payment.user_id)
                .values(stars_spent=case((spent < 0, 0), else_=spent))
            )
            if product and product.credits:
                await repo.add_credits(s, payment.user_id, -product.credits)
            if product and product.premium_days:
                until = await s.scalar(select(User.premium_until).where(User.id == payment.user_id))
                if until:
                    new_until = until - timedelta(days=product.premium_days)
                    await repo.set_fields(s, payment.user_id, premium_until=new_until if new_until > now else None)
        return f"✅ Возвращено {payment.amount} ⭐ пользователю {payment.user_id}."
