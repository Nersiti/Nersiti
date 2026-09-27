"""Telegram Stars purchases: validation, invoices, idempotent granting, refunds."""

import logging
import math
from datetime import date, datetime

from aiogram import Bot
from aiogram.types import LabeledPrice, SuccessfulPayment
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.game import economy, player_service
from app.game.clan_service import MILITIA
from app.game.errors import GameError
from app.game.shop_items import (
    CLAN_PALETTE,
    COINS_BAG_HOURS,
    COINS_BAG_MIN,
    ITEMS_BY_ID,
    SHIELD_DURATION,
    SUBSCRIPTION_PERIOD_SECONDS,
    VIP_PERIOD,
    ShopItem,
)
from app.i18n import t
from app.models import Clan, Payment, Sector, User, UserBoost

log = logging.getLogger(__name__)

SEP = "|"


def build_payload(item_id: str, user_id: int, param: str | None) -> str:
    payload = SEP.join([item_id, str(user_id), param or ""])
    if len(payload.encode()) > 128:
        raise GameError("bad_param")
    return payload


def parse_payload(payload: str) -> tuple[ShopItem, int, str | None]:
    try:
        item_id, user_id, param = payload.split(SEP)
        return ITEMS_BY_ID[item_id], int(user_id), param or None
    except (ValueError, KeyError) as exc:
        raise GameError("bad_payload") from exc


def coins_bag_amount(user: User) -> int:
    return max(COINS_BAG_MIN, user.income_per_hour * COINS_BAG_HOURS)


async def _boost(session: AsyncSession, user_id: int, boost_id: str) -> UserBoost:
    boost = await session.get(UserBoost, (user_id, boost_id), with_for_update=True)
    if boost is None:
        boost = UserBoost(user_id=user_id, boost_id=boost_id, uses_today=0)
        session.add(boost)
    return boost


async def uses_today(session: AsyncSession, user_id: int, item_id: str, today: date) -> int:
    boost = await session.get(UserBoost, (user_id, item_id))
    if boost is None or boost.uses_date != today:
        return 0
    return boost.uses_today


async def user_clan_if_owner(session: AsyncSession, user: User) -> Clan:
    clan = await session.get(Clan, user.clan_id) if user.clan_id else None
    if clan is None or clan.kind == MILITIA or clan.owner_user_id != user.id:
        raise GameError("not_clan_owner", 403)
    return clan


async def shield_limit_check(
    session: AsyncSession, user: User, h3: str, now: datetime, lock: bool = False
) -> Sector:
    stmt = select(Sector).where(Sector.h3 == h3)
    if lock:
        stmt = stmt.with_for_update()
    sector = (await session.execute(stmt)).scalar_one_or_none()
    if sector is None or user.clan_id is None or sector.owner_clan_id != user.clan_id:
        raise GameError("sector_not_owned")
    already = sector.shield_until is not None and sector.shield_until > now
    if not already:
        held = (
            await session.execute(
                select(func.count()).select_from(Sector).where(Sector.owner_clan_id == user.clan_id)
            )
        ).scalar_one()
        shielded = (
            await session.execute(
                select(func.count())
                .select_from(Sector)
                .where(Sector.owner_clan_id == user.clan_id, Sector.shield_until > now)
            )
        ).scalar_one()
        if shielded >= max(1, math.floor(held * economy.SHIELD_MAX_SHARE)):
            raise GameError("shield_limit")
    return sector


async def apply_shield(session: AsyncSession, user: User, h3: str, now: datetime) -> Sector:
    sector = await shield_limit_check(session, user, h3, now, lock=True)
    base = sector.shield_until if sector.shield_until and sector.shield_until > now else now
    sector.shield_until = base + SHIELD_DURATION
    return sector


async def check_purchase(
    session: AsyncSession, user: User, item: ShopItem, param: str | None, now: datetime
) -> None:
    if item.admin_only and user.id not in get_settings().admin_id_set:
        raise GameError("item_not_found", 404)
    if item.daily_limit is not None:
        if await uses_today(session, user.id, item.id, now.date()) >= item.daily_limit:
            raise GameError("daily_limit", 409)
    if item.clan_owner_only:
        await user_clan_if_owner(session, user)
    if item.param == "sector":
        if not param:
            raise GameError("bad_param")
        await shield_limit_check(session, user, param, now)
    elif item.param == "color":
        if param not in CLAN_PALETTE:
            raise GameError("bad_param")
    elif param:
        raise GameError("bad_param")


async def create_invoice(
    session: AsyncSession, bot: Bot, user: User, item_id: str, param: str | None, lang: str
) -> str:
    item = ITEMS_BY_ID.get(item_id)
    if item is None:
        raise GameError("item_not_found", 404)
    now = player_service.utcnow()
    await check_purchase(session, user, item, param, now)
    return await bot.create_invoice_link(
        title=t(lang, f"shop.{item.id}.title"),
        description=t(lang, f"shop.{item.id}.desc"),
        payload=build_payload(item.id, user.id, param),
        currency="XTR",
        prices=[LabeledPrice(label=t(lang, f"shop.{item.id}.title"), amount=item.stars)],
        subscription_period=SUBSCRIPTION_PERIOD_SECONDS if item.subscription else None,
    )


async def grant(
    session: AsyncSession,
    user: User,
    item: ShopItem,
    param: str | None,
    now: datetime,
    subscription_expiration: datetime | None = None,
) -> str:
    """Applies the purchase to a locked user row. Returns an i18n key for the reply."""
    player_service.sync_user(user, now)
    result_key = f"shop.{item.id}.done"

    if item.id == "coins_bag":
        player_service.credit(user, coins_bag_amount(user))
    elif item.id == "energy_refill":
        user.energy = user.energy_max
        user.energy_updated_at = now
    elif item.id == "artillery":
        boost = await _boost(session, user.id, "artillery")
        base = boost.until if boost.until and boost.until > now else now
        boost.until = base + item.duration
    elif item.id == "shield":
        try:
            await apply_shield(session, user, param or "", now)
        except GameError:
            # The sector was lost between checkout and payment: compensate with coins.
            player_service.credit(user, coins_bag_amount(user))
            result_key = "shop.shield.compensated"
    elif item.id == "autocollector":
        base = (
            user.offline_cap_until
            if user.offline_cap_until and user.offline_cap_until > now
            else now
        )
        user.offline_cap_until = base + item.duration
    elif item.id == "vip":
        base = user.vip_until if user.vip_until and user.vip_until > now else now
        user.vip_until = max(subscription_expiration or base + VIP_PERIOD, base + VIP_PERIOD)
    elif item.id == "clan_color":
        clan = await session.get(Clan, user.clan_id) if user.clan_id else None
        if clan is not None and param in CLAN_PALETTE:
            clan.color = param
    elif item.id == "clan_promo":
        clan = await session.get(Clan, user.clan_id) if user.clan_id else None
        if clan is not None:
            base = clan.promoted_until if clan.promoted_until and clan.promoted_until > now else now
            clan.promoted_until = base + item.duration
    elif item.id == "test_star":
        player_service.credit(user, 1)

    if item.daily_limit is not None or item.id == "artillery":
        boost = await _boost(session, user.id, item.id)
        if boost.uses_date != now.date():
            boost.uses_date = now.date()
            boost.uses_today = 0
        boost.uses_today += 1
    return result_key


async def process_successful_payment(
    session: AsyncSession, payer_id: int, payment: SuccessfulPayment, now: datetime
) -> tuple[bool, str | None]:
    """Records the payment and grants the item exactly once per charge id.
    Returns (granted_now, reply i18n key)."""
    item, user_id, param = parse_payload(payment.invoice_payload)
    inserted = await session.execute(
        insert(Payment)
        .values(
            user_id=payer_id,
            item_id=item.id,
            stars=payment.total_amount,
            telegram_payment_charge_id=payment.telegram_payment_charge_id,
            payload=payment.invoice_payload,
            status="paid",
            is_subscription=bool(payment.subscription_expiration_date),
            subscription_expiration=(
                datetime.fromtimestamp(payment.subscription_expiration_date, tz=now.tzinfo)
                if payment.subscription_expiration_date
                else None
            ),
            created_at=now,
        )
        .on_conflict_do_nothing(index_elements=[Payment.telegram_payment_charge_id])
        .returning(Payment.id)
    )
    if inserted.scalar_one_or_none() is None:
        return False, None  # duplicate delivery
    if user_id != payer_id:
        log.warning("payment payload user %s != payer %s", user_id, payer_id)
    user = await session.get(User, payer_id, with_for_update=True)
    if user is None:
        return True, None
    expiration = (
        datetime.fromtimestamp(payment.subscription_expiration_date, tz=now.tzinfo)
        if payment.subscription_expiration_date
        else None
    )
    key = await grant(session, user, item, param, now, subscription_expiration=expiration)
    return True, key


async def refund(session: AsyncSession, bot: Bot, charge_id: str) -> Payment:
    payment = (
        await session.execute(
            select(Payment).where(Payment.telegram_payment_charge_id == charge_id).with_for_update()
        )
    ).scalar_one_or_none()
    if payment is None:
        raise GameError("payment_not_found", 404)
    if payment.status == "refunded":
        return payment
    await bot.refund_star_payment(user_id=payment.user_id, telegram_payment_charge_id=charge_id)
    payment.status = "refunded"
    user = await session.get(User, payment.user_id, with_for_update=True)
    now = player_service.utcnow()
    if user is not None:
        # Best-effort revocation of time-based perks; spent coins cannot be taken back.
        if payment.item_id == "vip":
            user.vip_until = now
        elif payment.item_id == "autocollector":
            user.offline_cap_until = now
    return payment
