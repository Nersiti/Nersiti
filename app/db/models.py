from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.utils import utcnow


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(64), index=True)
    first_name: Mapped[str] = mapped_column(String(128), default="")
    language_code: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    # кошелёк
    crystals: Mapped[int] = mapped_column(Integer, default=0)
    premium_until: Mapped[datetime | None] = mapped_column(DateTime, index=True)  # статус «Лорд»
    sub_charge_id: Mapped[str | None] = mapped_column(String(128))
    sub_canceled: Mapped[bool] = mapped_column(Boolean, default=False)

    # дневные лимиты
    counters_date: Mapped[date | None] = mapped_column(Date)
    quills_today: Mapped[int] = mapped_column(Integer, default=0)
    battles_today: Mapped[int] = mapped_column(Integer, default=0)
    bonus_date: Mapped[date | None] = mapped_column(Date)

    # игра
    rating: Mapped[int] = mapped_column(Integer, default=1000, index=True)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    words_created: Mapped[int] = mapped_column(Integer, default=0)
    week_points: Mapped[int] = mapped_column(Integer, default=0, index=True)  # турнир недели

    # рост и удержание
    referrer_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    referral_rewarded: Mapped[bool] = mapped_column(Boolean, default=False)
    ref_earned: Mapped[int] = mapped_column(Integer, default=0)
    ref_day: Mapped[date | None] = mapped_column(Date)  # лимит реферальных наград в день
    ref_day_count: Mapped[int] = mapped_column(Integer, default=0)
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime)
    lord_notice_until: Mapped[datetime | None] = mapped_column(DateTime)
    source: Mapped[str | None] = mapped_column(String(64), index=True)

    stars_spent: Mapped[int] = mapped_column(Integer, default=0)
    rub_spent: Mapped[int] = mapped_column(Integer, default=0)  # копейки

    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)


class Card(Base):
    """A word someone owns, turned into a creature."""

    __tablename__ = "cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word: Mapped[str] = mapped_column(String(48), unique=True)  # нормализованное слово — ключ «владения»
    display: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(12), default="creating", index=True)  # creating | active
    owner_id: Mapped[int] = mapped_column(BigInteger, index=True)
    creator_id: Mapped[int] = mapped_column(BigInteger)

    name: Mapped[str] = mapped_column(String(48), default="")
    title: Mapped[str] = mapped_column(String(64), default="")
    element: Mapped[str] = mapped_column(String(12), default="")
    klass: Mapped[str] = mapped_column(String(12), default="")
    rarity: Mapped[str] = mapped_column(String(12), default="common", index=True)
    atk: Mapped[int] = mapped_column(Integer, default=0)
    def_: Mapped[int] = mapped_column("def", Integer, default=0)
    hp: Mapped[int] = mapped_column(Integer, default=0)
    ability: Mapped[str] = mapped_column(String(64), default="")
    ability_text: Mapped[str] = mapped_column(String(255), default="")
    lore: Mapped[str] = mapped_column(Text, default="")
    art_prompt: Mapped[str] = mapped_column(Text, default="")
    file_id: Mapped[str | None] = mapped_column(String(255))
    has_art: Mapped[bool] = mapped_column(Boolean, default=False)
    quill_paid: Mapped[int] = mapped_column(Integer, default=0)  # вернуть, если создание карты оборвалось

    level: Mapped[int] = mapped_column(Integer, default=1)
    xp: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    value: Mapped[int] = mapped_column(Integer, default=0, index=True)  # цена захвата в кристаллах

    protected_until: Mapped[datetime | None] = mapped_column(DateTime)
    shield_until: Mapped[datetime | None] = mapped_column(DateTime)
    revenge_to: Mapped[int | None] = mapped_column(BigInteger, index=True)  # кому напомнить «можно отбить»
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    owned_since: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Battle(Base):
    __tablename__ = "battles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(12))  # friendly | capture
    attacker_id: Mapped[int] = mapped_column(BigInteger, index=True)
    defender_id: Mapped[int] = mapped_column(BigInteger, index=True)
    attacker_card_id: Mapped[int] = mapped_column(Integer)
    defender_card_id: Mapped[int] = mapped_column(Integer, index=True)
    attacker_won: Mapped[bool] = mapped_column(Boolean)
    stake: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Offer(Base):
    """Buyout offer: the buyer's crystals are held until the owner responds."""

    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    card_id: Mapped[int] = mapped_column(Integer, index=True)
    buyer_id: Mapped[int] = mapped_column(BigInteger, index=True)
    seller_id: Mapped[int] = mapped_column(BigInteger, index=True)
    price: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(12), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Auction(Base):
    __tablename__ = "auctions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    word: Mapped[str] = mapped_column(String(48), index=True)
    display: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(12), default="active", index=True)  # active | finished | empty
    top_bid: Mapped[int] = mapped_column(Integer, default=0)
    top_bidder_id: Mapped[int | None] = mapped_column(BigInteger)
    bids_count: Mapped[int] = mapped_column(Integer, default=0)
    starts_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ends_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    card_id: Mapped[int | None] = mapped_column(Integer)


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("provider", "external_id", name="uq_payment_external"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    provider: Mapped[str] = mapped_column(String(16))  # stars | tg_rub | yookassa
    product_code: Mapped[str] = mapped_column(String(32))
    amount: Mapped[int] = mapped_column(Integer)  # звёзды или копейки
    currency: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    external_id: Mapped[str | None] = mapped_column(String(128))
    provider_charge_id: Mapped[str | None] = mapped_column(String(128))
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)


class PromoCode(Base):
    __tablename__ = "promo_codes"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    crystals: Mapped[int] = mapped_column(Integer, default=0)
    premium_days: Mapped[int] = mapped_column(Integer, default=0)
    max_uses: Mapped[int] = mapped_column(Integer, default=0)  # 0 — без ограничений
    used: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PromoUse(Base):
    __tablename__ = "promo_uses"
    __table_args__ = (UniqueConstraint("code", "user_id", name="uq_promo_use"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class KeyValue(Base):
    __tablename__ = "kv"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
