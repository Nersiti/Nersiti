from __future__ import annotations

from urllib.parse import quote

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from app import texts
from app.db.models import Auction, Card
from app.products import CATALOG, Product
from app.services.channels import Channel

BTN_CLAIM = "✒️ Захватить слово"
BTN_CARDS = "🃏 Мои слова"
BTN_ARENA = "⚔️ Арена"
BTN_AUCTION = "🔨 Аукцион"
BTN_TOP = "🏆 Топ"
BTN_SHOP = "💎 Магазин"
BTN_PROFILE = "👤 Профиль"
BTN_BONUS = "🎁 Бонусы"

PAGE_SIZE = 8


class MenuCb(CallbackData, prefix="m"):
    action: str


class ClaimCb(CallbackData, prefix="w"):
    w: str  # само слово или «~токен», если слово не помещается в 64 байта callback_data


class CardCb(CallbackData, prefix="c"):
    id: int
    action: str  # view | fight | capture | offer | shield | redraw | report


class AdminCardCb(CallbackData, prefix="ac"):
    id: int


class FightCb(CallbackData, prefix="f"):
    mine: int
    target: int
    capture: bool


class ArenaCb(CallbackData, prefix="a"):
    mine: int


class OfferCb(CallbackData, prefix="o"):
    card: int
    price: int


class OfferReplyCb(CallbackData, prefix="or"):
    id: int
    accept: bool


class BidCb(CallbackData, prefix="b"):
    auction: int
    amount: int


class PageCb(CallbackData, prefix="p"):
    page: int


class BuyCb(CallbackData, prefix="buy"):
    code: str


class PayCb(CallbackData, prefix="pay"):
    code: str
    method: str


class CheckCb(CallbackData, prefix="chk"):
    pid: int


class SubCb(CallbackData, prefix="sub"):
    action: str  # cancel | resume


class BroadcastCb(CallbackData, prefix="bc"):
    action: str  # go | cancel


def _b(text: str, cb: CallbackData) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=cb.pack())


def main_kb() -> ReplyKeyboardMarkup:
    rows = [(BTN_CLAIM, BTN_CARDS), (BTN_ARENA, BTN_AUCTION), (BTN_TOP, BTN_SHOP), (BTN_PROFILE, BTN_BONUS)]
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=a), KeyboardButton(text=b)] for a, b in rows],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Напиши любое слово…",
    )


def url_kb(text: str, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, url=url)]])


def claim_kb(value: str, paid_price: int) -> InlineKeyboardMarkup:
    label = "✒️ Захватить!" if not paid_price else f"✒️ Захватить за {paid_price} 💎"
    return InlineKeyboardMarkup(inline_keyboard=[[_b(label, ClaimCb(w=value))]])


def claim_value(display: str, put_token) -> str:  # type: ignore[no-untyped-def]
    """The word goes straight into the button (survives a bot restart); a long one — through a token."""
    try:
        ClaimCb(w=display).pack()
        return display
    except ValueError:
        return "~" + put_token(display)


def card_link_kb(card_id: int, text: str = "🃏 К слову") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_b(text, CardCb(id=card_id, action="view"))]])


def share_button(card: Card) -> InlineKeyboardButton:
    return InlineKeyboardButton(text="📤 Показать друзьям", switch_inline_query=card.display)


def card_kb(
    card: Card, viewer_id: int, shield_price: int, redraw_price: int, capture_lock: str | None = None
) -> InlineKeyboardMarkup:
    if card.owner_id == viewer_id:
        redraw = "🎨 Дорисовать арт" if not card.has_art else f"🎨 Перерисовать · {redraw_price} 💎"
        rows = [
            [_b(f"🛡 Щит · {shield_price} 💎", CardCb(id=card.id, action="shield")), _b("⚔️ В бой", ArenaCb(mine=card.id))],
            [share_button(card)],
            [_b(redraw, CardCb(id=card.id, action="redraw"))],
        ]
    else:
        capture = f"🔒 {capture_lock}" if capture_lock else f"🏴 Захватить · {card.value} 💎"
        rows = [
            [_b("⚔️ Бой", CardCb(id=card.id, action="fight")), _b(capture, CardCb(id=card.id, action="capture"))],
            [_b("💰 Предложить выкуп", CardCb(id=card.id, action="offer"))],
            [share_button(card), _b("🚩", CardCb(id=card.id, action="report"))],
        ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def fighters_kb(mine: list[Card], target: Card, capture: bool) -> InlineKeyboardMarkup:
    rows = [[_b(texts.card_button(c), FightCb(mine=c.id, target=target.id, capture=capture))] for c in mine]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def arena_kb(mine: list[Card]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_b(texts.card_button(c), ArenaCb(mine=c.id))] for c in mine])


def after_battle_kb(outcome_target: Card, my_card: Card) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_b("🔁 Реванш", FightCb(mine=my_card.id, target=outcome_target.id, capture=False)), _b("🎲 Новый соперник", ArenaCb(mine=my_card.id))],
            [_b("🃏 Карта соперника", CardCb(id=outcome_target.id, action="view"))],
        ]
    )


def collection_kb(cards: list[Card], page: int, pages: int) -> InlineKeyboardMarkup:
    rows = [[_b(texts.card_button(c), CardCb(id=c.id, action="view"))] for c in cards]
    nav = []
    if page > 0:
        nav.append(_b("⬅️", PageCb(page=page - 1)))
    if page < pages - 1:
        nav.append(_b("➡️", PageCb(page=page + 1)))
    if nav:
        rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def offer_kb(card: Card) -> InlineKeyboardMarkup:
    base = max(card.value, 10)
    prices = sorted({base // 2, base, base * 3 // 2, base * 2, base * 3})
    buttons = [_b(f"{p} 💎", OfferCb(card=card.id, price=p)) for p in prices if p > 0]
    return InlineKeyboardMarkup(inline_keyboard=[buttons[:3], buttons[3:]] if len(buttons) > 3 else [buttons])


def offer_reply_kb(offer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_b("✅ Продать", OfferReplyCb(id=offer_id, accept=True)), _b("❌ Отказать", OfferReplyCb(id=offer_id, accept=False))]]
    )


def auction_kb(a: Auction, min_bid: int) -> InlineKeyboardMarkup:
    steps = [min_bid, round(min_bid * 1.25), round(min_bid * 1.5)]
    buttons = [_b(f"{amount} 💎", BidCb(auction=a.id, amount=amount)) for amount in dict.fromkeys(steps)]
    return InlineKeyboardMarkup(inline_keyboard=[buttons, [_b("🔄 Обновить", MenuCb(action="auction"))]])


def first_card_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_b("⚔️ На арену", MenuCb(action="arena")), _b("🎁 Позвать друзей", MenuCb(action="bonus"))]]
    )


def shop_link_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_b("💎 Магазин", MenuCb(action="shop"))]])


def admin_card_kb(card_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_b("🗑 Удалить карту", AdminCardCb(id=card_id)), _b("🃏 Открыть", CardCb(id=card_id, action="view"))]]
    )


def no_crystals_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_b("💎 Купить кристаллы", MenuCb(action="shop"))],
            [_b("🎁 Получить бесплатно", MenuCb(action="bonus"))],
        ]
    )


def shop_kb(methods: list[str]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_b(texts.product_button(p, methods), BuyCb(code=p.code))] for p in CATALOG]
    )


def methods_kb(product: Product, methods: list[str]) -> InlineKeyboardMarkup:
    rows = []
    if "stars" in methods:
        suffix = " / мес" if product.subscription else ""
        rows.append([_b(f"⭐ Telegram Stars — {product.stars} ⭐{suffix}", PayCb(code=product.code, method="stars"))])
    if "tg_rub" in methods:
        rows.append([_b(f"💳 Картой в Telegram — {product.rub} ₽", PayCb(code=product.code, method="tg_rub"))])
    if "yookassa" in methods:
        rows.append([_b(f"💳 Карта / СБП — {product.rub} ₽", PayCb(code=product.code, method="yookassa"))])
    rows.append([_b("⬅️ Назад", MenuCb(action="shop"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def yookassa_kb(url: str, payment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💳 Оплатить", url=url)], [_b("✅ Проверить оплату", CheckCb(pid=payment_id))]]
    )


def profile_kb(has_subscription: bool, sub_canceled: bool) -> InlineKeyboardMarkup:
    rows = [[_b("💎 Магазин", MenuCb(action="shop")), _b("🎁 Бонусы", MenuCb(action="bonus"))]]
    if has_subscription:
        if sub_canceled:
            rows.append([_b("🔁 Включить автопродление", SubCb(action="resume"))])
        else:
            rows.append([_b("🔕 Отключить автопродление", SubCb(action="cancel"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def bonus_kb(link: str, share_text: str, can_claim: bool) -> InlineKeyboardMarkup:
    share_url = f"https://t.me/share/url?url={quote(link)}&text={quote(share_text)}"
    rows = []
    if can_claim:
        rows.append([_b("🎁 Забрать ежедневный бонус", MenuCb(action="daily"))])
    rows.append([InlineKeyboardButton(text="📤 Пригласить друзей", url=share_url)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def channels_kb(channels: list[Channel]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"📢 Подписаться — канал {i}", url=ch.url)] for i, ch in enumerate(channels, 1)]
    rows.append([_b("✅ Проверить подписку", MenuCb(action="check_sub"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def broadcast_confirm_kb(count: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_b(f"✅ Разослать ({count})", BroadcastCb(action="go")), _b("❌ Отмена", BroadcastCb(action="cancel"))]]
    )
