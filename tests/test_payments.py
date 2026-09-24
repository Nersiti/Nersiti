from __future__ import annotations

from datetime import timedelta

from aiogram.methods import (
    AnswerPreCheckoutQuery,
    CreateInvoiceLink,
    EditUserStarSubscription,
    RefundStarPayment,
    SendInvoice,
    SendMessage,
)
from sqlalchemy import select

from app import keyboards as kb
from app.db.models import Payment
from app.products import PRODUCTS
from app.utils import utcnow
from tests.conftest import ADMIN_ID, BotHarness
from tests.fake import callback_update, message_update, payment_update, pre_checkout_update
from tests.test_game import claim


async def test_stars_crystal_pack_purchase(harness: BotHarness) -> None:
    base = harness.ctx.settings.start_crystals
    await harness.feed(message_update("/start", user_id=100))
    await harness.feed(callback_update(kb.BuyCb(code="cr100").pack(), user_id=100))

    invoice = harness.session.of(SendInvoice)[0]
    assert invoice.currency == "XTR" and invoice.prices[0].amount == 50 and not invoice.provider_token
    assert invoice.payload == "cr100:100"

    await harness.feed(pre_checkout_update("cr100:100", "XTR", 50))
    await harness.feed(pre_checkout_update("cr100:100", "XTR", 1))
    assert [a.ok for a in harness.session.of(AnswerPreCheckoutQuery)] == [True, False]

    await harness.feed(payment_update("cr100:100", "XTR", 50, "charge-1"))
    await harness.feed(payment_update("cr100:100", "XTR", 50, "charge-1"))  # повторная доставка
    user = await harness.user(100)
    assert user.crystals == base + 100 and user.stars_spent == 50
    assert any("Оплата прошла" in t for t in harness.session.texts())
    assert any(r.chat_id == ADMIN_ID and "charge-1" in r.text for r in harness.session.of(SendMessage))


async def test_lord_subscription_and_renewal(harness: BotHarness) -> None:
    s = harness.ctx.settings
    await harness.feed(message_update("/start", user_id=100))
    await harness.feed(callback_update(kb.BuyCb(code="lord_month").pack(), user_id=100))
    link = harness.session.of(CreateInvoiceLink)[0]
    assert link.subscription_period == 30 * 24 * 3600 and link.currency == "XTR" and link.prices[0].amount == 249

    expires = int((utcnow() + timedelta(days=30)).timestamp()) + 10**4
    await harness.feed(
        payment_update(
            "lord_month:100", "XTR", 249, "sub-1",
            subscription_expiration_date=expires, is_recurring=True, is_first_recurring=True,
        )
    )
    user = await harness.user(100)
    first_until = user.premium_until
    assert first_until is not None and first_until > utcnow() + timedelta(days=29)
    assert user.sub_charge_id == "sub-1" and user.crystals == s.start_crystals + s.lord_bonus_crystals

    await harness.feed(
        payment_update(
            "lord_month:100", "XTR", 249, "sub-2", subscription_expiration_date=expires + 30 * 86400, is_recurring=True
        )
    )
    user = await harness.user(100)
    assert user.premium_until >= first_until + timedelta(days=29) and user.sub_charge_id == "sub-1"
    assert any("продлён" in t for t in harness.session.texts())

    await harness.feed(callback_update(kb.SubCb(action="cancel").pack(), user_id=100))
    edit = harness.session.of(EditUserStarSubscription)[0]
    assert edit.telegram_payment_charge_id == "sub-1" and edit.is_canceled
    assert (await harness.user(100)).sub_canceled


async def test_lord_gets_more_quills(harness_factory) -> None:  # type: ignore[no-untyped-def]
    h = await harness_factory(free_quills_per_day=1, lord_quills_per_day=5, start_crystals=0, lord_bonus_crystals=0)
    await h.feed(message_update("/start", user_id=100))
    await h.feed(payment_update("lord_week:100", "XTR", 79, "c-week"))
    for word in ("гроза в мае", "лужа", "пирожок"):
        await claim(h, 100, word)
    user = await h.user(100)
    assert user.quills_today == 3 and user.words_created == 3 and user.crystals == 0


async def test_referral_commission_on_purchase(harness: BotHarness) -> None:
    s = harness.ctx.settings
    await harness.feed(message_update("/start", user_id=100))
    await harness.feed(message_update("/start ref_100", user_id=200))
    await harness.feed(payment_update("cr1000:200", "XTR", 399, "c-1000", user_id=200))
    assert (await harness.user(100)).crystals == s.start_crystals + 1000 * s.ref_percent // 100


async def test_refund_stars(harness: BotHarness) -> None:
    await harness.feed(message_update("/start", user_id=100))
    await harness.feed(payment_update("cr300:100", "XTR", 139, "c-300"))
    await harness.feed(message_update("/refund c-300", user_id=ADMIN_ID))

    refund = harness.session.of(RefundStarPayment)[0]
    assert refund.user_id == 100 and refund.telegram_payment_charge_id == "c-300"
    user = await harness.user(100)
    assert user.crystals == harness.ctx.settings.start_crystals and user.stars_spent == 0
    async with harness.ctx.db.session() as s:
        assert (await s.scalar(select(Payment.status))) == "refunded"


async def test_rub_via_telegram_provider(harness_factory) -> None:  # type: ignore[no-untyped-def]
    h = await harness_factory(rub_provider_token="381764678:TEST:1", rub_receipt=True)
    await h.feed(message_update("/start", user_id=100))
    await h.feed(callback_update(kb.BuyCb(code="cr300").pack(), user_id=100))
    assert "способ оплаты" in h.session.texts()[-1]

    await h.feed(callback_update(kb.PayCb(code="cr300", method="tg_rub").pack(), user_id=100))
    invoice = h.session.of(SendInvoice)[0]
    assert invoice.currency == "RUB" and invoice.prices[0].amount == 24900
    assert invoice.provider_token == "381764678:TEST:1" and '"vat_code": 1' in invoice.provider_data

    await h.feed(pre_checkout_update("cr300:100", "RUB", 24900))
    assert h.session.of(AnswerPreCheckoutQuery)[0].ok
    await h.feed(payment_update("cr300:100", "RUB", 24900, "rub-1"))
    user = await h.user(100)
    assert user.crystals == h.ctx.settings.start_crystals + 300 and user.rub_spent == 24900


class FakeYooKassa:
    def __init__(self) -> None:
        self.status = "pending"
        self.value = "249.00"

    async def create_payment(self, amount_rub, description, metadata, idempotence_key):  # type: ignore[no-untyped-def]
        return {"id": "yk-1", "status": "pending", "confirmation": {"confirmation_url": "https://yoomoney.ru/pay"}}

    async def get_payment(self, payment_id):  # type: ignore[no-untyped-def]
        return {
            "id": payment_id,
            "status": self.status,
            "paid": self.status == "succeeded",
            "amount": {"value": self.value, "currency": "RUB"},
        }

    async def close(self) -> None:
        return None


async def test_yookassa_payment_flow(harness: BotHarness) -> None:
    yk = FakeYooKassa()
    harness.ctx.payments.yookassa = yk  # type: ignore[assignment]
    await harness.feed(message_update("/start", user_id=100))
    await harness.feed(callback_update(kb.PayCb(code="cr300", method="yookassa").pack(), user_id=100))
    link_msg = harness.session.of(SendMessage)[-1]
    assert link_msg.reply_markup.inline_keyboard[0][0].url == "https://yoomoney.ru/pay"
    check = link_msg.reply_markup.inline_keyboard[1][0].callback_data

    await harness.feed(callback_update(check, user_id=100))
    assert (await harness.user(100)).crystals == harness.ctx.settings.start_crystals

    yk.status = "succeeded"
    await harness.feed(callback_update(check, user_id=100))
    await harness.feed(callback_update(check, user_id=100))
    user = await harness.user(100)
    assert user.crystals == harness.ctx.settings.start_crystals + 300 and user.rub_spent == 24900


async def test_yookassa_amount_mismatch_not_credited(harness: BotHarness) -> None:
    yk = FakeYooKassa()
    yk.status, yk.value = "succeeded", "1.00"
    harness.ctx.payments.yookassa = yk  # type: ignore[assignment]
    await harness.feed(message_update("/start", user_id=100))
    payment_id, _ = await harness.ctx.payments.create_yookassa_payment(100, PRODUCTS["cr300"])
    status, fulfillment = await harness.ctx.payments.check_yookassa_payment(payment_id)
    assert status == "mismatch" and fulfillment is None
    assert (await harness.user(100)).crystals == harness.ctx.settings.start_crystals


async def test_banned_user_payment_still_recorded(harness: BotHarness) -> None:
    await harness.feed(message_update("/start", user_id=100))
    await harness.feed(message_update("/ban 100", user_id=ADMIN_ID))
    harness.session.clear()
    await harness.feed(message_update("кофе", user_id=100))
    assert not harness.session.of(SendMessage)
    await harness.feed(pre_checkout_update("cr100:100", "XTR", 50))
    assert harness.session.of(AnswerPreCheckoutQuery)[0].ok is False
    await harness.feed(payment_update("cr100:100", "XTR", 50, "late-charge"))
    assert (await harness.user(100)).stars_spent == 50
