from __future__ import annotations

from urllib.parse import quote

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app import texts
from app.products import CATALOG, Product
from app.services.channels import Channel
from app.services.images import RATIOS, STYLES

BTN_CHAT = "💬 ИИ-чат"
BTN_IMAGE = "🎨 Картинка"
BTN_PROFILE = "👤 Профиль"
BTN_BUY = "💎 Premium"
BTN_BONUS = "🎁 Бесплатно"
BTN_SETTINGS = "⚙️ Настройки"
MENU_BUTTONS = {BTN_CHAT, BTN_IMAGE, BTN_PROFILE, BTN_BUY, BTN_BONUS, BTN_SETTINGS}


class MenuCb(CallbackData, prefix="m"):
    action: str


class BuyCb(CallbackData, prefix="buy"):
    code: str


class PayCb(CallbackData, prefix="pay"):
    code: str
    method: str


class CheckCb(CallbackData, prefix="chk"):
    pid: int


class StyleCb(CallbackData, prefix="st"):
    code: str


class RatioCb(CallbackData, prefix="rt"):
    code: str


class RegenCb(CallbackData, prefix="rg"):
    token: str


class SubCb(CallbackData, prefix="sub"):
    action: str  # cancel | resume


class BroadcastCb(CallbackData, prefix="bc"):
    action: str  # go | cancel


def main_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_CHAT), KeyboardButton(text=BTN_IMAGE)],
            [KeyboardButton(text=BTN_PROFILE), KeyboardButton(text=BTN_BUY)],
            [KeyboardButton(text=BTN_BONUS), KeyboardButton(text=BTN_SETTINGS)],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Спроси что угодно…",
    )


def _button(text: str, cb: CallbackData) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=cb.pack())


def url_kb(text: str, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, url=url)]])


def chat_mode_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_button("🧹 Новый диалог", MenuCb(action="new"))]])


def image_mode_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_button("🖌 Стиль", MenuCb(action="style")), _button("📐 Формат", MenuCb(action="ratio"))]]
    )


def settings_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button("🖌 Стиль картинок", MenuCb(action="style")), _button("📐 Формат", MenuCb(action="ratio"))],
            [_button("🧹 Новый диалог", MenuCb(action="new")), _button("❓ Помощь", MenuCb(action="help"))],
        ]
    )


def styles_kb(current: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for code, style in STYLES.items():
        mark = "✅ " if code == current else ""
        builder.button(text=mark + style.label, callback_data=StyleCb(code=code))
    builder.adjust(2)
    return builder.as_markup()


def ratios_kb(current: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for code, (label, _, _) in RATIOS.items():
        mark = "✅ " if code == current else ""
        builder.button(text=mark + label, callback_data=RatioCb(code=code))
    builder.adjust(3)
    return builder.as_markup()


def image_result_kb(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button("🔁 Ещё вариант", RegenCb(token=token)), _button("🖌 Стиль", MenuCb(action="style"))],
        ]
    )


def no_funds_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button("💎 Купить Premium / кредиты", MenuCb(action="buy"))],
            [_button("🎁 Получить кредиты бесплатно", MenuCb(action="bonus"))],
        ]
    )


def upsell_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_button("💎 Premium", MenuCb(action="buy"))]])


def shop_kb(methods: list[str]) -> InlineKeyboardMarkup:
    rows = [[_button(texts.product_button(p, methods), BuyCb(code=p.code))] for p in CATALOG]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def methods_kb(product: Product, methods: list[str]) -> InlineKeyboardMarkup:
    rows = []
    if "stars" in methods:
        suffix = " / мес (автопродление)" if product.subscription else ""
        rows.append([_button(f"⭐ Telegram Stars — {product.stars} ⭐{suffix}", PayCb(code=product.code, method="stars"))])
    if "tg_rub" in methods:
        rows.append([_button(f"💳 Картой в Telegram — {product.rub} ₽", PayCb(code=product.code, method="tg_rub"))])
    if "yookassa" in methods:
        rows.append([_button(f"💳 Карта / СБП — {product.rub} ₽", PayCb(code=product.code, method="yookassa"))])
    rows.append([_button("⬅️ Назад", MenuCb(action="buy"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def yookassa_kb(url: str, payment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", url=url)],
            [_button("✅ Я оплатил", CheckCb(pid=payment_id))],
        ]
    )


def profile_kb(has_subscription: bool, sub_canceled: bool) -> InlineKeyboardMarkup:
    rows = [[_button("💎 Premium / кредиты", MenuCb(action="buy")), _button("🎁 Бесплатно", MenuCb(action="bonus"))]]
    if has_subscription:
        if sub_canceled:
            rows.append([_button("🔁 Включить автопродление", SubCb(action="resume"))])
        else:
            rows.append([_button("🔕 Отключить автопродление", SubCb(action="cancel"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def bonus_kb(link: str, share_text: str, can_claim: bool) -> InlineKeyboardMarkup:
    share_url = f"https://t.me/share/url?url={quote(link)}&text={quote(share_text)}"
    rows = []
    if can_claim:
        rows.append([_button("🎁 Забрать ежедневный бонус", MenuCb(action="daily"))])
    rows.append([InlineKeyboardButton(text="📤 Пригласить друзей", url=share_url)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def channels_kb(channels: list[Channel]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"📢 Подписаться — канал {i}", url=ch.url)] for i, ch in enumerate(channels, 1)
    ]
    rows.append([_button("✅ Я подписался", MenuCb(action="check_sub"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def broadcast_confirm_kb(count: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_button(f"✅ Разослать ({count})", BroadcastCb(action="go")), _button("❌ Отмена", BroadcastCb(action="cancel"))]
        ]
    )
