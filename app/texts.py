"""All bot texts in one place — edit freely."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from app.config import Settings
from app.game.rules import CLASSES, ELEMENTS, RARITIES, level_multiplier
from app.game.service import GameError, is_lord, protection_until, public_name
from app.utils import esc, fmt_dt, plural, utcnow

if TYPE_CHECKING:
    from app.db.models import Auction, Card, User
    from app.db.repo import SourceRow, Stats
    from app.game.service import BattleOutcome
    from app.products import Product
    from app.services.payments.service import Fulfillment


def cr(n: int) -> str:
    return f"{n} 💎"


def words_word(n: int) -> str:
    return plural(n, "слово", "слова", "слов")


# ---------- старт и правила ----------


def welcome(name: str, s: Settings, world: int) -> str:
    return (
        f"👋 {esc(name)}, добро пожаловать в <b>{esc(s.bot_name)}</b>!\n\n"
        "Здесь можно <b>завладеть любым словом мира</b>. Навсегда.\n\n"
        "✒️ Напиши слово — если его ещё никто не занял, оно станет твоим. Нейросеть превратит его "
        "в уникальное существо и нарисует карту.\n"
        "⚔️ Сражайся картами, захватывай чужие слова, выкупай их и защищай свои.\n"
        "🔨 Каждый день — аукцион легендарного слова.\n\n"
        f"🌍 Уже занято слов: <b>{world}</b>. Остальные ждут хозяина.\n\n"
        f"🎁 Держи {cr(s.start_crystals)} на старт. Каждый день — {s.free_quills_per_day} бесплатных пера.\n\n"
        "👇 <b>Напиши любое слово прямо сейчас.</b> Например: <i>бывший</i>, <i>пробка</i>, <i>Wi-Fi в метро</i>"
    )


def rules_text(s: Settings) -> str:
    return (
        f"📖 <b>Правила «{esc(s.bot_name)}»</b>\n\n"
        "<b>✒️ Слова.</b> Напиши любое слово или фразу до 4 слов. Если оно свободно, захвати его пером. "
        f"Бесплатно {s.free_quills_per_day} пера в день, дальше — {cr(s.quill_price)} за перо. "
        "Нейросеть создаст существо: стихия, класс, способность, характеристики. "
        "Редкость выпадает случайно: ⚪ обычная, 🔵 редкая, 🟣 эпическая, 🟠 легендарная, 🔴 мифическая.\n\n"
        "<b>⚔️ Бои.</b> Выбери свою карту и сразись с любой чужой. Победы дают опыт, карта растёт в уровне "
        f"и дорожает. Бесплатно {s.free_battles_per_day} боёв в день, дальше — {cr(s.battle_price)}.\n"
        "Стихии: 🔥 → 🌿 → 🪨 → ⚡ → 💧 → 🔥 (каждая сильнее следующей), ✨ и 🌑 сильны друг против друга.\n\n"
        "<b>🏴 Захват.</b> Чтобы отобрать слово, поставь его ценность в кристаллах и победи в бою. "
        "Ставка в любом случае уходит владельцу, поэтому на твоё слово нападают — ты богатеешь. "
        f"После захвата у слова {s.immunity_hours} ч иммунитета. Щит защищает ещё на {s.shield_days} дня.\n\n"
        "<b>💰 Выкуп.</b> Предложи владельцу цену — кристаллы замораживаются, пока он решает. "
        f"Комиссия игры {s.fee_percent}% (для Лордов {s.lord_fee_percent}%).\n\n"
        "<b>🔨 Аукцион.</b> Самые «горячие» слова (любовь, деньги, пятница…) нельзя захватить — "
        "они разыгрываются на аукционе по одному в день. Победитель получает легендарную или мифическую карту.\n\n"
        f"<b>👑 Лорд</b> — {s.lord_quills_per_day} перьев и {s.lord_battles_per_day} боёв в день, "
        "выше шанс легендарок, меньше комиссия.\n\n"
        "📤 Показывай карты друзьям: в любом чате набери <code>@</code>имя_бота и слово.\n\n"
        "Команды: /start /rules /top /auction /buy /bonus /profile /terms /paysupport"
    )


def terms(s: Settings) -> str:
    return (
        "📄 <b>Условия использования</b>\n\n"
        f"1. «{esc(s.bot_name)}» — развлекательная игра. Карты, слова и кристаллы — игровые объекты, "
        "они не являются имуществом, ценными бумагами или деньгами и не выводятся из игры.\n"
        "2. Платные услуги: кристаллы и статус «Лорд». Это цифровые услуги, они начисляются сразу после оплаты.\n"
        "3. «Лорд», оплаченный Telegram Stars, продлевается автоматически каждые 30 дней, пока вы не отключите "
        "автопродление в профиле или в настройках Telegram.\n"
        "4. Возврат: если услуга не оказана из-за технического сбоя, напишите в /paysupport в течение 14 дней.\n"
        "5. Запрещено создавать слова с оскорблениями, политикой, именами реальных людей, контентом 18+. "
        "Такие карты удаляются, за нарушения доступ ограничивается без возврата средств.\n"
        "6. Мы храним ваш Telegram ID и имя для работы игры. Ваше имя видно другим игрокам в топе и на картах.\n"
        "7. Условия могут обновляться, актуальная версия — по команде /terms."
    )


def paysupport(s: Settings) -> str:
    contact = esc(s.support_contact) if s.support_contact else "администратору бота"
    return (
        "🛟 <b>Поддержка по оплате</b>\n\n"
        f"Если оплата прошла, а кристаллы или статус не начислились, либо нужен возврат, напишите {contact}.\n"
        "Укажите ваш ID (есть в «👤 Профиль») и время оплаты. Отвечаем в течение 24 часов."
    )


MAIN_MENU_HINT = "Выбери действие в меню 👇 или просто напиши слово."
CLAIM_HINT = (
    "✒️ <b>Напиши любое слово или фразу</b> (до 4 слов) — проверю, свободно ли оно.\n\n"
    "Идеи: <i>дедлайн в пятницу</i>, <i>бабушкин пирожок</i>, <i>пробка на МКАДе</i>, <i>кот хозяина</i>"
)
NOT_A_WORD = "🤔 Это не похоже на слово. Пиши буквами, до 4 слов и до 32 символов."
ONLY_TEXT = "Я понимаю только слова ✍️ Напиши любое слово — проверю, свободно ли оно."
BUSY = "⏳ Подожди, нейросеть ещё создаёт твою предыдущую карту."


# ---------- слова и карты ----------


def word_free(display: str, quills_left: int, price: int) -> str:
    cost = (
        f"Бесплатных перьев сегодня: <b>{quills_left}</b>."
        if quills_left > 0
        else f"Бесплатные перья на сегодня кончились — перо стоит <b>{cr(price)}</b>."
    )
    return (
        f"✨ Слово <b>«{esc(display)}»</b> никому не принадлежит!\n\n"
        f"Захвати его — и оно станет твоим навсегда. {cost}"
    )


def word_reserved(display: str, on_auction: bool, s: Settings) -> str:
    text = f"🔥 <b>«{esc(display)}»</b> — легендарное слово. Его нельзя захватить пером, только выиграть на аукционе."
    if on_auction:
        text += "\n\n🔨 Прямо сейчас оно на аукционе! Жми «🔨 Аукцион»."
    else:
        text += f"\n\nКаждый день в {s.auction_start_hour}:00 на аукцион выходит одно такое слово."
    return text


def word_creating(display: str) -> str:
    return f"⏳ Слово «{esc(display)}» прямо сейчас захватывает другой игрок. Опоздал на секунды!"


def creating(display: str, load: int) -> str:
    text = (
        f"✒️ Вписываю <b>«{esc(display)}»</b> в историю мира…\n"
        "🧠 Нейросеть придумывает существо и рисует карту (20–60 секунд)."
    )
    if load > 0:
        text += f"\n⏳ Перед тобой в очереди: {load}"
    return text


def created(card: Card) -> str:
    r = RARITIES[card.rarity]
    head = {
        "mythic": "🔴🔴🔴 <b>МИФИЧЕСКАЯ КАРТА!</b> Такое выпадает раз на двести слов!",
        "legendary": "🟠🟠 <b>ЛЕГЕНДАРНАЯ КАРТА!</b>",
        "epic": "🟣 Эпическая карта!",
    }.get(card.rarity, f"{r.emoji} {r.label} карта.")
    return (
        f"{head}\n\n🎉 Слово <b>«{esc(card.display)}»</b> теперь твоё. Навсегда.\n"
        "Его могут попытаться захватить — не забывай про щит 🛡"
    )


def card_caption(card: Card, owner: User | None, s: Settings, viewer_id: int | None = None) -> str:
    r = RARITIES[card.rarity]
    e = ELEMENTS[card.element]
    k = CLASSES[card.klass]
    m = level_multiplier(card.level)
    if viewer_id and owner and owner.id == viewer_id:
        owner_line = "👑 Владелец: <b>ты</b>"
    else:
        owner_line = f"👑 Владелец: {esc(public_name(owner))}{' 👑' if owner and is_lord(owner) else ''}"
    lines = [
        f"🃏 <b>«{esc(card.display)}»</b> · №{card.id}",
        f"<b>{esc(card.name)}</b>{', ' + esc(card.title) if card.title else ''}",
        f"{r.emoji} {r.label} · {e.emoji} {e.label} · {k.label} ({k.perk}) · ур. {card.level}",
        f"⚔️ {round(card.atk * m)}   🛡 {round(card.def_ * m)}   ❤️ {round(card.hp * m)}",
        f"✦ <b>{esc(card.ability)}</b> — {esc(card.ability_text)}",
    ]
    if card.lore:
        lines.append(f"📜 <i>{esc(card.lore)}</i>")
    lines += ["", owner_line, f"🏆 Побед: {card.wins} · поражений: {card.losses}", f"💎 Ценность: {card.value}"]
    until = protection_until(card)
    if until and until > utcnow():
        lines.append(f"🛡 Под защитой до {fmt_dt(until, s.tz)}")
    text = "\n".join(lines)
    if len(text) > 1024 and card.lore:  # подпись к фото — максимум 1024 символа
        text = text.replace(f"📜 <i>{esc(card.lore)}</i>\n", "")
    return text[:1024]


def no_crystals(need: int) -> str:
    return (
        f"💎 Нужно {cr(need)}, а на балансе не хватает.\n\n"
        "Кристаллы можно купить в «💎 Магазин» (от 50 ⭐) или получить бесплатно в «🎁 Бонусы»."
    )


ERRORS = {
    "taken": "😱 Кто-то оказался быстрее и уже захватил это слово! Посмотри, кто владелец, и отбери его в бою.",
    "mine": "Это слово уже твоё 🙂",
    "reserved": "🔥 Это слово разыгрывается только на аукционе.",
    "not_found": "Карта не найдена.",
    "not_owner": "Это не твоя карта.",
    "own_card": "Это твоя собственная карта 🙂",
    "changed": "Слово только что сменило владельца или получило щит. Попробуй ещё раз.",
    "gpu_offline": "🎨 Художник сейчас отдыхает (видеокарта недоступна). Попробуй позже — кристаллы возвращены.",
    "offer_exists": "Ты уже сделал предложение за эту карту. Дождись ответа владельца.",
    "offer_gone": "Это предложение уже неактуально.",
    "bad_price": "Некорректная цена.",
    "auction_closed": "Аукцион уже закончился.",
    "already_top": "Твоя ставка и так самая высокая 👑",
    "bid_race": "Кто-то только что перебил ставку. Обнови аукцион и попробуй снова.",
    "auction_exists": "Это слово уже на аукционе.",
}


def error_text(err: GameError, s: Settings) -> str:
    if err.code == "no_crystals":
        return no_crystals(int(err.data.get("need", 0)))  # type: ignore[call-overload]
    if err.code == "forbidden":
        reason = esc(str(err.data.get("reason", "нарушает правила")))
        return f"🙅 Это слово нельзя захватить: {reason}. Перо возвращено."
    if err.code == "protected":
        until = err.data.get("until")
        when = fmt_dt(until, s.tz) if isinstance(until, datetime) else "—"
        return f"🛡 Слово под защитой до {when}. Захватить пока нельзя, но можно сразиться просто так."
    if err.code == "bid_too_low":
        return f"Минимальная ставка сейчас: {cr(int(err.data.get('need', 0)))}"  # type: ignore[call-overload]
    return ERRORS.get(err.code, "Что-то пошло не так. Попробуй ещё раз.")


FORBIDDEN_WORD = "🙅 Такое слово захватить нельзя: оно нарушает правила игры."
CREATE_FAILED = "😔 Не получилось создать карту. Перо возвращено — попробуй ещё раз через минуту."


# ---------- коллекция ----------


def collection(count: int, total: int, page: int, pages: int) -> str:
    if count == 0:
        return "🃏 У тебя пока нет ни одного слова.\n\nНапиши любое слово — и захвати его первым!"
    return (
        f"🃏 <b>Твои слова: {count}</b> · общая ценность {cr(total)}\n"
        f"Страница {page + 1} из {pages}. Нажми на карту, чтобы открыть её."
    )


def card_button(card: Card) -> str:
    return f"{RARITIES[card.rarity].emoji} {card.display} · ур.{card.level} · {card.value}💎"


# ---------- бои ----------


def choose_fighter(target: Card, capture: bool) -> str:
    if capture:
        return (
            f"🏴 <b>Захват слова «{esc(target.display)}»</b>\n"
            f"Ставка: {cr(target.value)} — уйдёт владельцу при любом исходе. Победишь — слово твоё.\n\n"
            "Выбери свою карту:"
        )
    return f"⚔️ Выбери свою карту для боя против <b>«{esc(target.display)}»</b>:"


NEED_CARD = "Сначала захвати хотя бы одно слово: просто напиши его мне ✒️"
ARENA = "⚔️ <b>Арена</b>\n\nВыбери бойца — я найду ему достойного соперника."
NO_OPPONENTS = "На арене пока пусто — позови друзей, чтобы было с кем сразиться! (🎁 Бонусы → ссылка)"
BATTLE_STARTED = "⚔️ Бой начинается…"


def _hp_bar(left: int, total: int) -> str:
    filled = max(0, min(10, round(10 * left / total))) if total else 0
    return "🟩" * filled + "⬛" * (10 - filled)


def battle_result(o: BattleOutcome, s: Settings) -> str:
    a, d = o.attacker, o.defender
    won = o.result.attacker_won
    hp_a, hp_d = o.result.hp_left
    max_a, max_d = o.result.hp_max
    lines = [
        f"⚔️ <b>«{esc(a.display)}»</b> vs <b>«{esc(d.display)}»</b>",
        "",
        esc(o.story),
        "",
        f"«{esc(a.display)}» {_hp_bar(hp_a, max_a)} {hp_a}/{max_a}",
        f"«{esc(d.display)}» {_hp_bar(hp_d, max_d)} {hp_d}/{max_d}",
        "",
        ("🏆 <b>ПОБЕДА!</b>" if won else "💀 <b>Поражение.</b>")
        + f" Рейтинг {'+' if won else '−'}{o.rating_delta} · опыт +{o.xp_gain}",
    ]
    if o.level_up:
        lines.append(f"⬆️ «{esc(a.display)}» достигла {a.level} уровня! Ценность: {cr(a.value)}")
    if o.capture:
        if o.captured:
            lines.append(
                f"\n🏴 <b>Слово «{esc(d.display)}» захвачено!</b> Теперь оно твоё. "
                f"Иммунитет {s.immunity_hours} ч."
            )
        else:
            lines.append(f"\n🛡 Захват не удался. Ставка {cr(o.stake)} ушла владельцу.")
    return "\n".join(lines)


def defender_notice(o: BattleOutcome, attacker_name: str) -> str:
    d = o.defender
    if o.captured:
        return (
            f"🚨 <b>Игрок {esc(attacker_name)} захватил твоё слово «{esc(d.display)}»!</b>\n"
            f"Компенсация: +{cr(o.payout)}. Верни его, когда закончится иммунитет."
        )
    return (
        f"🛡 <b>Игрок {esc(attacker_name)} пытался захватить «{esc(d.display)}» — и проиграл!</b>\n"
        f"Его ставка твоя: +{cr(o.payout)}."
    )


def shield_bought(until: datetime, s: Settings) -> str:
    return f"🛡 Щит поднят! Слово защищено от захвата до {fmt_dt(until, s.tz)}."


# ---------- выкуп ----------


def offer_choose(card: Card) -> str:
    return (
        f"💰 <b>Выкуп «{esc(card.display)}»</b>\nЦенность карты: {cr(card.value)}.\n\n"
        "Сколько предложишь владельцу? Кристаллы заморозятся, пока он решает (до 24 ч)."
    )


def offer_sent(card: Card, price: int) -> str:
    return f"📨 Предложение {cr(price)} за «{esc(card.display)}» отправлено владельцу. Жди ответа!"


def offer_received(card: Card, price: int, buyer: str) -> str:
    return (
        f"💰 <b>{esc(buyer)} хочет купить твоё слово «{esc(card.display)}»</b> за {cr(price)}!\n"
        f"Ценность карты: {cr(card.value)}. Комиссия игры спишется с суммы сделки."
    )


def offer_accepted_buyer(card: Card) -> str:
    return f"🎉 Сделка! Слово <b>«{esc(card.display)}»</b> теперь твоё."


def offer_accepted_seller(card: Card, payout: int) -> str:
    return f"🤝 Слово «{esc(card.display)}» продано. +{cr(payout)}"


def offer_declined(price: int) -> str:
    return f"❌ Владелец отказался продавать. {cr(price)} вернулись к тебе."


def offer_expired(price: int) -> str:
    return f"⌛ Владелец не ответил на предложение за сутки. {cr(price)} вернулись к тебе."


OFFER_CANCELED = "Слово сменило владельца — твоё предложение отменено, кристаллы вернулись."


# ---------- аукцион ----------


def auction_view(a: Auction, top_name: str | None, min_bid: int, s: Settings, is_top: bool) -> str:
    lines = [
        f"🔨 <b>Аукцион: «{esc(a.display)}»</b>",
        "Победитель получит 🟠 легендарную или 🔴 мифическую карту этого слова.",
        "",
        f"💎 Ставка: <b>{a.top_bid or '—'}</b>" + (f" ({esc(top_name)})" if top_name else ""),
        f"📈 Ставок: {a.bids_count}",
        f"⏰ Окончание: {fmt_dt(a.ends_at, s.tz)}",
        f"Минимальная следующая ставка: {cr(min_bid)}",
    ]
    if is_top:
        lines.append("\n👑 Сейчас лидируешь ты!")
    lines.append(
        "\n<i>Если твою ставку перебьют, кристаллы вернутся. Ставка в последние минуты продлевает торги.</i>\n"
        "Своя ставка: <code>/bid 500</code>"
    )
    return "\n".join(lines)


def no_auction(s: Settings) -> str:
    return (
        "🔨 Сейчас аукциона нет.\n\n"
        f"Каждый день в {s.auction_start_hour}:00 на торги выходит одно легендарное слово — "
        f"любовь, деньги, пятница, дракон… Торги идут до {s.auction_end_hour}:00. Приходи!"
    )


def bid_ok(a: Auction) -> str:
    return f"✅ Твоя ставка {cr(a.top_bid)} на «{esc(a.display)}» лидирует!"


def outbid(a: Auction, returned: int) -> str:
    return (
        f"⚡ Твою ставку на «{esc(a.display)}» перебили: теперь {cr(a.top_bid)}.\n"
        f"{cr(returned)} вернулись на баланс. Успеешь перебить? /auction"
    )


def auction_refunded(display: str, price: int) -> str:
    return f"😔 Слово «{esc(display)}» не удалось выдать по итогам аукциона. Твоя ставка {cr(price)} возвращена."


def auction_won(card: Card, price: int) -> str:
    return f"🏆 <b>Ты выиграл аукцион!</b> Слово «{esc(card.display)}» твоё за {cr(price)}."


# ---------- топ ----------


def top(lords: list[tuple[User, int, int]], cards: list[Card], fighters: list[User], world: int) -> str:
    medals = ["🥇", "🥈", "🥉"] + [f"{i}." for i in range(4, 11)]
    lines = [f"🏆 <b>Топ мира слов</b> · занято слов: {world}\n", "<b>Богатейшие владельцы</b>"]
    for i, (user, total, count) in enumerate(lords):
        crown = " 👑" if is_lord(user) else ""
        lines.append(f"{medals[i]} {esc(public_name(user))}{crown} — {total} 💎 ({count} {words_word(count)})")
    lines.append("\n<b>Самые ценные слова</b>")
    for i, card in enumerate(cards):
        lines.append(f"{medals[i]} {RARITIES[card.rarity].emoji} «{esc(card.display)}» — {card.value} 💎")
    lines.append("\n<b>Лучшие бойцы</b>")
    for i, user in enumerate(fighters):
        lines.append(f"{medals[i]} {esc(public_name(user))} — {user.rating} ({user.wins}/{user.losses})")
    if not lords:
        lines.append("\nМир пока пуст — стань первым владельцем!")
    return "\n".join(lines)


# ---------- профиль ----------


def profile(user: User, s: Settings, count: int, total: int, quills: int, battles: int) -> str:
    lord = is_lord(user)
    status = f"👑 Лорд до {fmt_dt(user.premium_until, s.tz)}" if lord else "🙂 Игрок"
    if lord and user.sub_charge_id:
        status += "\n🔁 Автопродление: " + ("выключено" if user.sub_canceled else "включено")
    q_limit = s.lord_quills_per_day if lord else s.free_quills_per_day
    b_limit = s.lord_battles_per_day if lord else s.free_battles_per_day
    return (
        "👤 <b>Профиль</b>\n\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"💼 Статус: {status}\n"
        f"💎 Кристаллы: <b>{user.crystals}</b>\n\n"
        f"🃏 Слов: {count} · ценность {cr(total)}\n"
        f"✒️ Создано слов: {user.words_created}\n"
        f"⚔️ Рейтинг: {user.rating} · побед {user.wins} · поражений {user.losses}\n\n"
        "<b>Сегодня</b>\n"
        f"✒️ Перья: {quills}/{q_limit}\n"
        f"⚔️ Бои: {battles}/{b_limit}"
    )


# ---------- магазин ----------


def shop(s: Settings, methods: list[str]) -> str:
    pay = ["⭐ Telegram Stars"] if "stars" in methods else []
    if "tg_rub" in methods or "yookassa" in methods:
        pay.append("💳 карта / СБП")
    return (
        "💎 <b>Магазин</b>\n\n"
        "<b>👑 Лорд</b> — статус настоящего хозяина слов:\n"
        f"• {s.lord_quills_per_day} перьев в день (вместо {s.free_quills_per_day})\n"
        f"• {s.lord_battles_per_day} боёв в день (вместо {s.free_battles_per_day})\n"
        "• шанс легендарной и мифической карты почти в 2 раза выше\n"
        f"• комиссия {s.lord_fee_percent}% вместо {s.fee_percent}%\n"
        "• корона 👑 в топе, приоритет у художника, без рекламы\n"
        f"• +{cr(s.lord_bonus_crystals)} при каждой оплате\n\n"
        "<b>💎 Кристаллы</b> — перья, захваты, щиты, аукционы и выкуп чужих слов.\n\n"
        f"Оплата: {', '.join(pay) or '—'}"
    )


def product_button(p: Product, methods: list[str]) -> str:
    price = f"{p.stars} ⭐" if "stars" in methods else f"{p.rub} ₽"
    suffix = " / мес" if p.subscription and "stars" in methods else ""
    return f"{p.badge + ' ' if p.badge else ''}{p.title} — {price}{suffix}"


def choose_method(p: Product) -> str:
    return f"🛒 <b>{esc(p.title)}</b>\n\n{esc(p.description)}\n\nВыбери способ оплаты:"


def subscription_offer(p: Product) -> str:
    return f"👑 <b>{esc(p.title)}</b> — {p.stars} ⭐ в месяц\n\n{esc(p.description)}\n\nНажми кнопку ниже, чтобы оформить."


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
    lines = ["🔁 <b>Статус Лорда продлён.</b>\n"] if f.renewal else ["🎉 <b>Оплата прошла, спасибо!</b>\n"]
    if f.crystals:
        lines.append(f"💎 Начислено: <b>{f.crystals}</b>")
    if f.premium_until:
        lines.append(f"👑 Ты Лорд до <b>{fmt_dt(f.premium_until, s.tz)}</b>")
    lines.append("\nВопросы по оплате — /paysupport")
    return "\n".join(lines)


SUB_CANCELED = "🔕 Автопродление отключено. Статус Лорда сохранится до конца оплаченного периода."
SUB_RESUMED = "🔁 Автопродление снова включено."
SUB_ERROR = "Не удалось изменить подписку. Попробуй позже или управляй ей в настройках Telegram."


# ---------- бонусы и рефералы ----------


def referral_welcome(bonus: int) -> str:
    return f"🎁 Ты пришёл по приглашению друга — дарим <b>+{cr(bonus)}</b>!"


def referral_reward(bonus: int, friend: str) -> str:
    return f"🎉 Твой друг {esc(friend)} захватил первое слово по твоей ссылке — тебе <b>+{cr(bonus)}</b>!"


def referral_commission(bonus: int) -> str:
    return f"💸 Твой друг сделал покупку — тебе <b>+{cr(bonus)}</b>!"


def bonus_screen(s: Settings, link: str, referrals: int, earned: int, can_claim: bool) -> str:
    daily = "доступен ✅" if can_claim else "уже получен, возвращайся завтра"
    return (
        "🎁 <b>Бесплатные кристаллы</b>\n\n"
        f"<b>1. Ежедневный бонус</b> — +{cr(s.daily_bonus)} ({daily}).\n\n"
        f"<b>2. Друзья</b> — +{cr(s.ref_bonus_inviter)} за каждого друга, который захватит первое слово, "
        f"другу +{cr(s.ref_bonus_invitee)} на старте, и {s.ref_percent}% от всех его покупок — навсегда.\n"
        f"Твоя ссылка:\n<code>{esc(link)}</code>\n"
        f"Приглашено: <b>{referrals}</b> · заработано: <b>{cr(earned)}</b>\n\n"
        "<b>3. Промокоды</b> — отправь <code>/promo КОД</code>. Ищи их в канале игры.\n\n"
        "<b>4. Пусть на твои слова нападают</b> — ставка за неудачный захват достаётся тебе."
    )


def share_text(s: Settings) -> str:
    return f"В игре «{s.bot_name}» можно навсегда завладеть любым словом. Займи своё, пока не забрали 👀"


def daily_claimed(amount: int) -> str:
    return f"🎁 +{cr(amount)}! Возвращайся завтра."


DAILY_ALREADY = "Сегодня бонус уже получен. Возвращайся завтра 🙂"
PROMO_USAGE = "Отправь промокод так: <code>/promo КОД</code>"
PROMO_ERRORS = {
    "not_found": "❌ Такого промокода нет.",
    "expired": "⌛ Срок действия промокода истёк.",
    "used": "Ты уже активировал этот промокод.",
    "exhausted": "😔 Промокод закончился.",
}


def promo_ok(crystals: int, premium_days: int) -> str:
    parts = []
    if crystals:
        parts.append(f"+{cr(crystals)}")
    if premium_days:
        parts.append(f"👑 Лорд на {premium_days} {plural(premium_days, 'день', 'дня', 'дней')}")
    return "✅ Промокод активирован: " + ", ".join(parts)


SUBSCRIBE_REQUIRED = (
    "📢 Чтобы захватывать слова бесплатно, подпишись на канал(ы) ниже и нажми «✅ Я подписался».\n\n"
    "👑 Лордам подписка не нужна."
)
SUBSCRIBE_OK = "✅ Спасибо за подписку! Продолжай."
SUBSCRIBE_STILL_MISSING = "Подписка не найдена. Подпишись и нажми ещё раз."


def ad_block(ad_html: str) -> str:
    return f"📢 <b>Реклама</b>\n\n{ad_html}\n\n<i>Без рекламы — со статусом 👑 Лорд</i>"


# ---------- хроника (канал новостей) ----------


def news_new_card(card: Card, owner: str) -> str:
    r = RARITIES[card.rarity]
    return f"{r.emoji} <b>{r.label.upper()} КАРТА!</b>\nИгрок {esc(owner)} захватил слово «{esc(card.display)}»."


def news_capture(card: Card, attacker: str, defender: str) -> str:
    return f"🏴 <b>Захват!</b> Игрок {esc(attacker)} отобрал слово «{esc(card.display)}» у игрока {esc(defender)}."


def news_auction_start(a: Auction, s: Settings) -> str:
    return (
        f"🔨 <b>Аукцион дня: «{esc(a.display)}»</b>\n"
        f"Торги до {fmt_dt(a.ends_at, s.tz)}. Победитель получит легендарную карту этого слова."
    )


def news_auction_won(card: Card, price: int, owner: str) -> str:
    return f"🏆 Игрок {esc(owner)} выиграл аукцион и стал владельцем слова «{esc(card.display)}» за {cr(price)}!"


# ---------- админ ----------

ADMIN_HELP = (
    "\n\n<b>Команды администратора</b>\n"
    "/stats — статистика\n"
    "/sources — источники трафика и доход\n"
    "/link <code>тег</code> — ссылка для рекламы с отслеживанием\n"
    "/user <code>id|@username</code> — карточка игрока\n"
    "/give <code>id кол-во</code> — начислить кристаллы (минус — списать)\n"
    "/premium <code>id дней</code> — выдать статус Лорда\n"
    "/ban <code>id</code> · /unban <code>id</code>\n"
    "/delcard <code>слово</code> — удалить карту (нарушение правил)\n"
    "/auction_start <code>слово [часов]</code> — запустить аукцион сейчас\n"
    "/promo_new <code>КОД кристаллы [активаций] [дней_лорда] [дней_жизни]</code> · /promos\n"
    "/refund <code>charge_id</code> — вернуть звёзды\n"
    "/broadcast — ответь этой командой на сообщение для рассылки\n"
    "/setad <code>текст</code> | <code>/setad off</code> — реклама для игроков без статуса Лорда\n"
    "/channels — обязательная подписка (<code>set @a,@b</code> | <code>off</code> | <code>reset</code>)"
)


def admin_stats(st: Stats) -> str:
    return (
        "📊 <b>Статистика</b>\n\n"
        f"👥 Игроков: <b>{st.users_total}</b> (+{st.users_today} сегодня)\n"
        f"🔥 Активны сегодня: <b>{st.active_today}</b> · за 7 дней: {st.active_week}\n"
        f"👑 Лордов сейчас: <b>{st.premium_active}</b>\n"
        f"🚫 Заблокировали бота: {st.blocked}\n\n"
        f"🃏 Слов занято: {st.cards_total} (+{st.cards_today} сегодня) · ⚔️ боёв сегодня: {st.battles_today}\n\n"
        f"💰 Сегодня: {st.payments_today} оплат · {st.stars_today} ⭐ · {st.rub_today / 100:.0f} ₽\n"
        f"💰 Всего: {st.stars_total} ⭐ · {st.rub_total / 100:.0f} ₽ · платящих: {st.payers_total}"
    )


def admin_sources(rows: list[SourceRow]) -> str:
    if not rows:
        return "Пока нет данных."
    lines = ["📈 <b>Источники</b> (игроков / платящих / ⭐ / ₽)\n"]
    for r in rows:
        conv = f"{r.payers / r.users * 100:.1f}%" if r.users else "0%"
        lines.append(
            f"<code>{esc(r.source)}</code>: {r.users} / {r.payers} ({conv}) / {r.stars} ⭐ / {r.rub / 100:.0f} ₽"
        )
    return "\n".join(lines)


def admin_user(user: User, s: Settings, referrals: int, payments: tuple[int, int, int], cards: int) -> str:
    count, stars, kopecks = payments
    return (
        f"👤 <b>{esc(user.first_name)}</b> @{esc(user.username or '—')}\n"
        f"ID: <code>{user.id}</code>\n"
        f"Регистрация: {fmt_dt(user.created_at, s.tz)} · был: {fmt_dt(user.last_seen_at, s.tz)}\n"
        f"Источник: {esc(user.source or 'organic')} · пригласил: {user.referrer_id or '—'}\n"
        f"Кристаллы: {user.crystals} · Лорд до: {fmt_dt(user.premium_until, s.tz)}\n"
        f"Слов: {cards} · рейтинг {user.rating} · побед {user.wins}/{user.losses}\n"
        f"Платежей: {count} · {stars} ⭐ · {kopecks / 100:.0f} ₽\n"
        f"Рефералов: {referrals} · заработал: {user.ref_earned}\n"
        f"Бан: {'да' if user.is_banned else 'нет'} · заблокировал бота: {'да' if user.is_blocked else 'нет'}"
    )


def admin_payment(f: Fulfillment) -> str:
    price = f"{f.amount} ⭐" if f.currency == "XTR" else f"{f.amount / 100:.0f} ₽"
    renewal = " (автопродление)" if f.renewal else ""
    return (
        f"💰 <b>Оплата{renewal}</b>: {esc(f.product.title)} — {price}\n"
        f"Игрок: <code>{f.user_id}</code>\n"
        f"charge_id: <code>{esc(f.charge_id)}</code>"
    )
