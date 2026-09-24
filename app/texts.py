"""All bot texts in one place — edit freely."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.config import Settings
from app.products import CATALOG, Product
from app.services.billing import Kind, daily_limit, is_premium, used_today
from app.services.images import RATIOS, STYLES
from app.utils import credits_word, esc, fmt_dt, plural

if TYPE_CHECKING:
    from app.db.models import User
    from app.db.repo import SourceRow, Stats
    from app.services.payments.service import Fulfillment


def welcome(name: str, s: Settings) -> str:
    return (
        f"👋 Привет, {esc(name)}!\n\n"
        f"Я — <b>{esc(s.bot_name)}</b>, твой ИИ-помощник прямо в Telegram:\n\n"
        "💬 <b>Отвечаю на любые вопросы</b> — учёба, работа, код, тексты, идеи, переводы\n"
        "🎨 <b>Рисую картинки</b> по описанию — фото, арты, аниме, логотипы\n"
        "🧠 <b>Помню контекст</b> диалога, можно уточнять и спорить\n\n"
        f"🎁 Каждый день бесплатно: <b>{s.free_chat_per_day}</b> "
        f"{plural(s.free_chat_per_day, 'сообщение', 'сообщения', 'сообщений')} и "
        f"<b>{s.free_images_per_day}</b> {plural(s.free_images_per_day, 'картинка', 'картинки', 'картинок')}.\n"
        "💎 Нужно больше — загляни в «Premium».\n\n"
        "Просто напиши свой вопрос 👇 или нажми «🎨 Картинка»."
    )


def help_text(s: Settings) -> str:
    return (
        f"❓ <b>Как пользоваться {esc(s.bot_name)}</b>\n\n"
        "<b>💬 ИИ-чат</b> — просто пиши сообщения. Бот помнит контекст, "
        "команда /new начинает новый диалог.\n\n"
        "<b>🎨 Картинки</b> — нажми «🎨 Картинка» и опиши, что нарисовать. "
        "Или сразу: <code>/img кот-астронавт на Луне</code>\n"
        "Стиль и формат меняются в «⚙️ Настройки».\n\n"
        "<b>Лимиты</b>\n"
        f"• Бесплатно каждый день: {s.free_chat_per_day} сообщений и {s.free_images_per_day} картинки\n"
        f"• Сверх лимита: сообщение — {credits_word(s.chat_cost)}, картинка — {credits_word(s.image_cost)}\n"
        f"• 💎 Premium: до {s.premium_chat_per_day} сообщений и {s.premium_images_per_day} картинок в день\n\n"
        "<b>Бесплатные кредиты</b> — «🎁 Бесплатно»: ежедневный бонус, приглашение друзей, промокоды.\n\n"
        "Команды: /start /new /img /profile /buy /bonus /promo /terms /paysupport"
    )


def terms(s: Settings) -> str:
    return (
        "📄 <b>Условия использования</b>\n\n"
        f"1. {esc(s.bot_name)} предоставляет доступ к генерации текста и изображений нейросетями. "
        "Ответы ИИ могут содержать ошибки — проверяйте важную информацию.\n"
        "2. Платные услуги: кредиты и Premium-доступ. Это цифровые услуги, они начисляются сразу после оплаты.\n"
        "3. Premium, оплаченный Telegram Stars, продлевается автоматически каждые 30 дней, "
        "пока вы не отключите автопродление (в профиле бота или в настройках Telegram).\n"
        "4. Возврат: если услуга не была оказана (технический сбой, кредиты не потрачены) — "
        "напишите в /paysupport в течение 14 дней, мы вернём оплату или начислим кредиты.\n"
        "5. Запрещено генерировать незаконный контент, контент 18+, материалы, нарушающие права третьих лиц. "
        "За нарушения доступ может быть ограничен без возврата средств.\n"
        "6. Мы храним ваш Telegram ID, имя и историю диалога только для работы бота и не передаём их третьим лицам. "
        "История удаляется командой /new.\n"
        "7. Условия могут обновляться, актуальная версия всегда доступна по команде /terms."
    )


def paysupport(s: Settings) -> str:
    contact = esc(s.support_contact) if s.support_contact else "администратору бота"
    return (
        "🛟 <b>Поддержка по оплате</b>\n\n"
        f"Если оплата прошла, а кредиты или Premium не начислились, либо нужен возврат — напишите {contact}.\n"
        "Укажите ваш ID (есть в «👤 Профиль») и время оплаты. Отвечаем в течение 24 часов."
    )


MAIN_MENU_HINT = "Выбери действие в меню 👇"


def chat_mode() -> str:
    return "💬 <b>Режим ИИ-чата</b>\n\nЗадай любой вопрос — отвечу. Чтобы начать с чистого листа, нажми «🧹 Новый диалог»."


def image_mode(user: User) -> str:
    style = STYLES.get(user.image_style, STYLES["auto"]).label
    ratio = RATIOS.get(user.image_ratio, RATIOS["1x1"])[0]
    return (
        "🎨 <b>Режим картинок</b>\n\n"
        "Опиши, что нарисовать, — можно на русском. Чем подробнее, тем лучше.\n\n"
        "<i>Например: «рыжий кот в скафандре на фоне Земли, реалистичное фото»</i>\n\n"
        f"Стиль: <b>{style}</b> · Формат: <b>{ratio}</b>"
    )


def settings_screen(user: User) -> str:
    style = STYLES.get(user.image_style, STYLES["auto"]).label
    ratio = RATIOS.get(user.image_ratio, RATIOS["1x1"])[0]
    return f"⚙️ <b>Настройки</b>\n\n🖌 Стиль картинок: <b>{style}</b>\n📐 Формат: <b>{ratio}</b>"


CHOOSE_STYLE = "🖌 Выбери стиль картинок:"
CHOOSE_RATIO = "📐 Выбери формат картинок:"
DIALOG_CLEARED = "🧹 Готово! Начинаем новый диалог."
BUSY = "⏳ Подожди, я ещё работаю над предыдущим запросом."
LLM_ERROR = "😔 Нейросеть сейчас перегружена. Попробуй ещё раз через минуту — лимит не списан."
IMAGE_ERROR = "😔 Не получилось нарисовать. Попробуй ещё раз или измени описание — лимит не списан."
PROMPT_FORBIDDEN = "🙅 Такой запрос нарушает правила. Попробуй другое описание."
EMPTY_PROMPT = "✏️ Опиши, что нарисовать. Например: <code>/img замок в облаках на закате</code>"
REGEN_EXPIRED = "Запрос устарел — отправь описание заново."
ONLY_TEXT = "Пока я понимаю только текст ✍️ Напиши вопрос или опиши картинку."


def image_queued(load: int, premium: bool) -> str:
    text = "🎨 Рисую… обычно это 10–60 секунд."
    if load > 0:
        text += f"\nПеред тобой в очереди: {load}"
    if premium:
        text += "\n⚡ Premium: приоритетная очередь"
    return text


def image_caption(prompt: str, bot_username: str | None) -> str:
    caption = f"🎨 <i>{esc(prompt[:700])}</i>"
    if bot_username:
        caption += f"\n\n🤖 Создано в @{esc(bot_username)}"
    return caption


def no_funds(kind: Kind, s: Settings, premium: bool) -> str:
    what = "сообщений" if kind is Kind.CHAT else "картинок"
    cost = s.chat_cost if kind is Kind.CHAT else s.image_cost
    head = (
        f"⏳ Дневной лимит Premium на {what} исчерпан."
        if premium
        else f"😔 Бесплатные {what} на сегодня закончились."
    )
    return (
        f"{head}\n\nСверх лимита {'сообщение' if kind is Kind.CHAT else 'картинка'} стоит "
        f"<b>{credits_word(cost)}</b>, а на балансе недостаточно.\n\n"
        "Что можно сделать:\n"
        "💎 Купить Premium или кредиты — от 50 ⭐\n"
        f"🎁 Пригласить друга — +{s.ref_bonus_inviter} кредитов\n"
        "🕛 Или подождать до завтра — лимит обновится в полночь."
    )


def quota_hint(remaining: int, kind: Kind) -> str:
    what = (
        plural(remaining, "бесплатное сообщение", "бесплатных сообщения", "бесплатных сообщений")
        if kind is Kind.CHAT
        else plural(remaining, "бесплатная картинка", "бесплатные картинки", "бесплатных картинок")
    )
    if remaining == 0:
        return "ℹ️ Это был последний бесплатный запрос на сегодня. Больше — в 💎 Premium (/buy)."
    return f"ℹ️ Осталось {remaining} {what} на сегодня. Безлимит — в 💎 Premium (/buy)."


def ad_block(ad_html: str) -> str:
    return f"📢 <b>Реклама</b>\n\n{ad_html}\n\n<i>Без рекламы — в 💎 Premium</i>"


SUBSCRIBE_REQUIRED = (
    "📢 Чтобы пользоваться ботом бесплатно, подпишись на канал(ы) ниже и нажми «✅ Я подписался».\n\n"
    "💎 С Premium подписка не нужна."
)
SUBSCRIBE_OK = "✅ Спасибо за подписку! Можешь продолжать."
SUBSCRIBE_STILL_MISSING = "Подписка не найдена. Подпишись и нажми ещё раз."


def profile(user: User, s: Settings, referrals: int) -> str:
    chat_used, img_used = used_today(user, s)
    premium = is_premium(user)
    if premium:
        plan = f"💎 Premium до {fmt_dt(user.premium_until, s.tz)}"
        if user.sub_charge_id:
            plan += "\n🔁 Автопродление: " + ("выключено" if user.sub_canceled else "включено")
    else:
        plan = "🆓 Бесплатный"
    return (
        "👤 <b>Профиль</b>\n\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"💼 Тариф: {plan}\n"
        f"💰 Баланс: <b>{credits_word(user.credits)}</b>\n\n"
        "<b>Сегодня:</b>\n"
        f"💬 Сообщения: {chat_used} / {daily_limit(s, Kind.CHAT, premium)}\n"
        f"🎨 Картинки: {img_used} / {daily_limit(s, Kind.IMAGE, premium)}\n"
        f"<i>Сверх лимита: сообщение — {s.chat_cost}, картинка — {s.image_cost} кр.</i>\n\n"
        f"📈 Всего: {user.total_chat} сообщений, {user.total_images} картинок\n"
        f"👥 Приглашено друзей: {referrals}"
    )


def shop(s: Settings, methods: list[str]) -> str:
    pay = ["⭐ Telegram Stars"] if "stars" in methods else []
    if "tg_rub" in methods or "yookassa" in methods:
        pay.append("💳 карта / СБП")
    return (
        "💎 <b>Premium и кредиты</b>\n\n"
        "<b>Premium</b> — всё без ограничений:\n"
        f"• до {s.premium_chat_per_day} сообщений и {s.premium_images_per_day} картинок в день\n"
        "• ⚡ приоритетная очередь генерации\n"
        "• 🧠 длинная память диалога\n"
        "• 🚫 без рекламы и обязательных подписок\n\n"
        "<b>Кредиты</b> — если нужно иногда:\n"
        f"💬 сообщение = {credits_word(s.chat_cost)} · 🎨 картинка = {credits_word(s.image_cost)}\n"
        "Кредиты не сгорают.\n\n"
        f"Оплата: {', '.join(pay) or '—'}\n"
        "<i>Звёзды покупаются прямо в Telegram за пару касаний.</i>"
    )


def product_button(p: Product, methods: list[str]) -> str:
    price = f"{p.stars} ⭐" if "stars" in methods else f"{p.rub} ₽"
    suffix = " / мес" if p.subscription and "stars" in methods else ""
    return f"{p.badge + ' ' if p.badge else ''}{p.title} — {price}{suffix}"


def choose_method(p: Product) -> str:
    return f"🛒 <b>{esc(p.title)}</b>\n\n{esc(p.description)}\n\nВыбери способ оплаты:"


def subscription_offer(p: Product) -> str:
    return (
        f"🔥 <b>{esc(p.title)}</b> — {p.stars} ⭐ в месяц\n\n"
        f"{esc(p.description)}\n\nНажми кнопку ниже, чтобы оформить подписку."
    )


def yookassa_link(p: Product) -> str:
    return (
        f"💳 <b>{esc(p.title)}</b> — {p.rub} ₽\n\n"
        "1. Нажми «Оплатить» и заверши оплату картой или через СБП.\n"
        "2. Вернись в бот — начислим автоматически в течение минуты.\n"
        "Если не пришло — нажми «✅ Я оплатил»."
    )


PAYMENT_PENDING = "⏳ Оплата ещё не поступила. Если ты уже оплатил — подожди минуту и нажми ещё раз."
PAYMENT_CANCELED = "❌ Платёж отменён или истёк. Создай новый через /buy."
PAYMENT_UNAVAILABLE = "😔 Оплата этим способом временно недоступна. Попробуй другой способ."
PRECHECKOUT_FAIL = "Этот товар недоступен или цена изменилась. Открой магазин заново: /buy"
PAYMENT_UNKNOWN_PRODUCT = "✅ Оплата получена, но товар не распознан. Напиши в /paysupport — всё исправим."


def payment_success(f: Fulfillment, s: Settings) -> str:
    lines = ["🎉 <b>Оплата прошла, спасибо!</b>\n"]
    if f.renewal:
        lines = ["🔁 <b>Подписка Premium продлена.</b>\n"]
    if f.credits:
        lines.append(f"💰 Начислено: <b>{credits_word(f.credits)}</b>")
    if f.premium_until:
        lines.append(f"💎 Premium активен до <b>{fmt_dt(f.premium_until, s.tz)}</b>")
    lines.append("\nПриятной работы! Вопросы по оплате — /paysupport")
    return "\n".join(lines)


def referral_commission(bonus: int) -> str:
    return f"💸 Твой друг совершил покупку — тебе начислено <b>{credits_word(bonus)}</b>!"


def referral_reward(bonus: int, friend: str) -> str:
    return f"🎉 {esc(friend)} начал(а) пользоваться ботом по твоей ссылке — тебе <b>+{credits_word(bonus)}</b>!"


def referral_welcome(bonus: int) -> str:
    return f"🎁 Ты пришёл по приглашению друга — дарим <b>+{credits_word(bonus)}</b>!"


def bonus_screen(s: Settings, link: str, referrals: int, earned: int, can_claim: bool) -> str:
    daily = "доступен ✅" if can_claim else "уже получен сегодня, возвращайся завтра"
    return (
        "🎁 <b>Бесплатные кредиты</b>\n\n"
        f"<b>1. Ежедневный бонус</b> — +{credits_word(s.daily_bonus)} каждый день ({daily}).\n\n"
        f"<b>2. Приглашай друзей</b> — +{credits_word(s.ref_bonus_inviter)} за каждого друга, "
        f"а другу +{s.ref_bonus_invitee} на старте. "
        f"И ещё {s.ref_percent}% от всех его покупок — навсегда!\n"
        f"Твоя ссылка:\n<code>{esc(link)}</code>\n"
        f"Приглашено: <b>{referrals}</b> · Заработано: <b>{credits_word(earned)}</b>\n\n"
        "<b>3. Промокоды</b> — отправь <code>/promo КОД</code>. Ищи их в нашем канале и у блогеров."
    )


def share_text(s: Settings) -> str:
    return f"Попробуй {s.bot_name} — ИИ-чат и генерация картинок прямо в Telegram. Держи бонусные кредиты 🎁"


def daily_claimed(amount: int) -> str:
    return f"🎁 +{credits_word(amount)}! Возвращайся завтра за новым бонусом."


DAILY_ALREADY = "Сегодня бонус уже получен. Возвращайся завтра 🙂"
PROMO_USAGE = "Отправь промокод так: <code>/promo КОД</code>"
PROMO_ERRORS = {
    "not_found": "❌ Такого промокода нет.",
    "expired": "⌛ Срок действия промокода истёк.",
    "used": "Ты уже активировал этот промокод.",
    "exhausted": "😔 Промокод закончился.",
}


def promo_ok(credits: int, premium_days: int) -> str:
    parts = []
    if credits:
        parts.append(f"+{credits_word(credits)}")
    if premium_days:
        parts.append(f"Premium на {premium_days} {plural(premium_days, 'день', 'дня', 'дней')}")
    return "✅ Промокод активирован: " + ", ".join(parts)


SUB_CANCELED = "🔕 Автопродление отключено. Premium будет действовать до конца оплаченного периода."
SUB_RESUMED = "🔁 Автопродление снова включено."
SUB_ERROR = "Не удалось изменить подписку. Попробуй позже или управляй ей в настройках Telegram."


def showcase_caption(text: str, bot_name: str) -> str:
    return f"🎨 {esc(text)}\n\n<i>Нарисовано нейросетью {esc(bot_name)} за 20 секунд. Создай свою 👇</i>"


# ---------- admin ----------

ADMIN_HELP = (
    "\n\n<b>Команды администратора</b>\n"
    "/stats — статистика\n"
    "/sources — источники трафика и доход\n"
    "/link <code>тег</code> — ссылка для рекламы с отслеживанием\n"
    "/user <code>id|@username</code> — карточка пользователя\n"
    "/give <code>id кол-во</code> — начислить кредиты (минус — списать)\n"
    "/premium <code>id дней</code> — выдать Premium\n"
    "/ban <code>id</code> · /unban <code>id</code>\n"
    "/promo_new <code>КОД кредиты [активаций] [дней_premium] [дней_жизни]</code>\n"
    "/promos — список промокодов\n"
    "/refund <code>charge_id</code> — вернуть звёзды\n"
    "/broadcast — ответь этой командой на сообщение для рассылки\n"
    "/setad <code>текст</code> | <code>/setad off</code> — реклама для бесплатных пользователей\n"
    "/channels — обязательная подписка (<code>set @a,@b</code> | <code>off</code> | <code>reset</code>)\n"
    "/showcase — опубликовать пост в канал-витрину сейчас"
)


def admin_stats(st: Stats) -> str:
    return (
        "📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: <b>{st.users_total}</b> (+{st.users_today} сегодня)\n"
        f"🔥 Активны сегодня: <b>{st.active_today}</b> · за 7 дней: {st.active_week}\n"
        f"💎 Premium сейчас: <b>{st.premium_active}</b>\n"
        f"🚫 Заблокировали бота: {st.blocked}\n\n"
        f"💬 Сообщений сегодня: {st.chat_today} · 🎨 картинок: {st.images_today}\n\n"
        f"💰 Сегодня: {st.payments_today} оплат · {st.stars_today} ⭐ · {st.rub_today / 100:.0f} ₽\n"
        f"💰 Всего: {st.stars_total} ⭐ · {st.rub_total / 100:.0f} ₽ · платящих: {st.payers_total}"
    )


def admin_sources(rows: list[SourceRow]) -> str:
    if not rows:
        return "Пока нет данных."
    lines = ["📈 <b>Источники</b> (польз. / платящих / ⭐ / ₽)\n"]
    for r in rows:
        conv = f"{r.payers / r.users * 100:.1f}%" if r.users else "0%"
        lines.append(
            f"<code>{esc(r.source)}</code>: {r.users} / {r.payers} ({conv}) / {r.stars} ⭐ / {r.rub / 100:.0f} ₽"
        )
    return "\n".join(lines)


def admin_user(user: User, s: Settings, referrals: int, payments: tuple[int, int, int]) -> str:
    count, stars, kopecks = payments
    return (
        f"👤 <b>{esc(user.first_name)}</b> @{esc(user.username or '—')}\n"
        f"ID: <code>{user.id}</code>\n"
        f"Регистрация: {fmt_dt(user.created_at, s.tz)} · был: {fmt_dt(user.last_seen_at, s.tz)}\n"
        f"Источник: {esc(user.source or 'organic')} · пригласил: {user.referrer_id or '—'}\n"
        f"Кредиты: {user.credits} · Premium до: {fmt_dt(user.premium_until, s.tz)}\n"
        f"Всего: {user.total_chat} сообщений, {user.total_images} картинок\n"
        f"Платежей: {count} · {stars} ⭐ · {kopecks / 100:.0f} ₽\n"
        f"Рефералов: {referrals} · заработал: {user.ref_earned}\n"
        f"Бан: {'да' if user.is_banned else 'нет'} · заблокировал бота: {'да' if user.is_blocked else 'нет'}"
    )


def admin_payment(f: Fulfillment) -> str:
    price = f"{f.amount} ⭐" if f.currency == "XTR" else f"{f.amount / 100:.0f} ₽"
    renewal = " (автопродление)" if f.renewal else ""
    return (
        f"💰 <b>Оплата{renewal}</b>: {esc(f.product.title)} — {price}\n"
        f"Пользователь: <code>{f.user_id}</code>\n"
        f"charge_id: <code>{esc(f.charge_id)}</code>"
    )


def all_products_summary() -> str:
    return "\n".join(f"{p.code}: {p.title} — {p.stars}⭐ / {p.rub}₽" for p in CATALOG)
