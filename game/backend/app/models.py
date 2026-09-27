from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now_col(**kw: Any) -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), **kw)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str] = mapped_column(String(128), default="")
    last_name: Mapped[str | None] = mapped_column(String(128))
    language_code: Mapped[str | None] = mapped_column(String(16))
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    photo_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now_col()
    last_seen_at: Mapped[datetime] = _now_col()

    referrer_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    country_code: Mapped[str | None] = mapped_column(String(2), index=True)
    city_id: Mapped[int | None] = mapped_column(ForeignKey("cities.id"), index=True)
    clan_id: Mapped[int | None] = mapped_column(ForeignKey("clans.id"), index=True)
    clan_joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    coins: Mapped[int] = mapped_column(BigInteger, default=0)
    total_earned: Mapped[int] = mapped_column(BigInteger, default=0)
    passive_earned_total: Mapped[int] = mapped_column(BigInteger, default=0)
    level: Mapped[int] = mapped_column(SmallInteger, default=1)

    energy: Mapped[int] = mapped_column(Integer, default=0)
    energy_max: Mapped[int] = mapped_column(Integer, default=0)
    energy_updated_at: Mapped[datetime] = _now_col()
    multitap_level: Mapped[int] = mapped_column(SmallInteger, default=0)

    income_per_hour: Mapped[int] = mapped_column(BigInteger, default=0)
    attack_bonus_bp: Mapped[int] = mapped_column(Integer, default=0)
    defense_bonus_bp: Mapped[int] = mapped_column(Integer, default=0)
    last_passive_at: Mapped[datetime] = _now_col()
    last_tap_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    daily_streak: Mapped[int] = mapped_column(SmallInteger, default=0)
    daily_last_date: Mapped[date | None] = mapped_column(Date)

    vip_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    offline_cap_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ref_claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    season_score: Mapped[int] = mapped_column(BigInteger, default=0)
    notify_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    banned: Mapped[bool] = mapped_column(Boolean, default=False)
    suspicion: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        Index("ix_users_season_score", "season_score"),
        Index("ix_users_country_score", "country_code", "season_score"),
    )


class UserUpgrade(Base):
    __tablename__ = "user_upgrades"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    card_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    level: Mapped[int] = mapped_column(SmallInteger, default=0)


class City(Base):
    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name_en: Mapped[str] = mapped_column(String(200))
    name_ru: Mapped[str | None] = mapped_column(String(200))
    country_code: Mapped[str] = mapped_column(String(2), index=True)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    population: Mapped[int] = mapped_column(Integer)
    is_capital: Mapped[bool] = mapped_column(Boolean, default=False)
    sectors_count: Mapped[int] = mapped_column(Integer, default=0)
    controller_clan_id: Mapped[int | None] = mapped_column(Integer, index=True)

    __table_args__ = (Index("ix_cities_lat_lng", "lat", "lng"),)


# Prefix search: WHERE lower(name_ru) LIKE 'каз%'
Index(
    "ix_cities_name_en_prefix",
    func.lower(City.name_en).label("name_en_lower"),
    postgresql_ops={"name_en_lower": "text_pattern_ops"},
)
Index(
    "ix_cities_name_ru_prefix",
    func.lower(City.name_ru).label("name_ru_lower"),
    postgresql_ops={"name_ru_lower": "text_pattern_ops"},
)


class Sector(Base):
    __tablename__ = "sectors"

    h3: Mapped[str] = mapped_column(String(16), primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"), index=True)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    value: Mapped[int] = mapped_column(SmallInteger, default=1)
    owner_clan_id: Mapped[int | None] = mapped_column(ForeignKey("clans.id"), index=True)
    defense: Mapped[int] = mapped_column(BigInteger, default=0)
    defense_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shield_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_actor_id: Mapped[int | None] = mapped_column(BigInteger)

    __table_args__ = (Index("ix_sectors_lat_lng", "lat", "lng"),)


class Clan(Base):
    __tablename__ = "clans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # "militia" | "channel" | "group"
    kind: Mapped[str] = mapped_column(String(16))
    tg_chat_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    title: Mapped[str] = mapped_column(String(128))
    username: Mapped[str | None] = mapped_column(String(64))
    invite_link: Mapped[str | None] = mapped_column(Text)
    photo_path: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str] = mapped_column(String(7), default="#888888")
    owner_user_id: Mapped[int | None] = mapped_column(BigInteger)
    city_id: Mapped[int | None] = mapped_column(ForeignKey("cities.id"))
    members_count: Mapped[int] = mapped_column(Integer, default=0)
    subscribers_only: Mapped[bool] = mapped_column(Boolean, default=False)
    season_points: Mapped[int] = mapped_column(BigInteger, default=0)
    promoted_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    banned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _now_col()

    __table_args__ = (
        # One militia per city.
        Index(
            "uq_clans_militia_city",
            "city_id",
            unique=True,
            postgresql_where=text("kind = 'militia'"),
        ),
        Index("ix_clans_season_points", "season_points"),
    )


class BattleLog(Base):
    __tablename__ = "battle_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = _now_col(index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    clan_id: Mapped[int] = mapped_column(Integer)
    sector_h3: Mapped[str] = mapped_column(String(16))
    city_id: Mapped[int] = mapped_column(Integer)
    # "capture" | "attack" | "reinforce"
    action: Mapped[str] = mapped_column(String(16))
    amount: Mapped[int] = mapped_column(BigInteger)
    power: Mapped[int] = mapped_column(BigInteger)
    flipped: Mapped[bool] = mapped_column(Boolean, default=False)
    prev_owner_clan_id: Mapped[int | None] = mapped_column(Integer)
    # Who held the sector before a flip (receives the "your sector was captured" message).
    prev_actor_id: Mapped[int | None] = mapped_column(BigInteger)

    __table_args__ = (Index("ix_battle_log_prev_owner", "prev_owner_clan_id", "created_at"),)


class Referral(Base):
    __tablename__ = "referrals"

    invitee_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    inviter_id: Mapped[int] = mapped_column(BigInteger, index=True)
    created_at: Mapped[datetime] = _now_col()
    l3_rewarded: Mapped[bool] = mapped_column(Boolean, default=False)
    passive_snapshot: Mapped[int] = mapped_column(BigInteger, default=0)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # "channel_sub" | "link"
    kind: Mapped[str] = mapped_column(String(16))
    title_ru: Mapped[str] = mapped_column(String(200))
    title_en: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(Text)
    tg_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    reward: Mapped[int] = mapped_column(BigInteger)
    # "pending" | "active" | "done" | "rejected"
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    max_completions: Mapped[int | None] = mapped_column(Integer)
    completions: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sponsor_user_id: Mapped[int | None] = mapped_column(BigInteger)
    stars_paid: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = _now_col()


class UserTask(Base):
    __tablename__ = "user_tasks"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True
    )
    completed_at: Mapped[datetime] = _now_col()


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    item_id: Mapped[str] = mapped_column(String(32))
    stars: Mapped[int] = mapped_column(Integer)
    telegram_payment_charge_id: Mapped[str] = mapped_column(String(128), unique=True)
    payload: Mapped[str] = mapped_column(Text)
    # "paid" | "refunded"
    status: Mapped[str] = mapped_column(String(16), default="paid")
    is_subscription: Mapped[bool] = mapped_column(Boolean, default=False)
    subscription_expiration: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now_col(index=True)


class UserBoost(Base):
    __tablename__ = "user_boosts"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    boost_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    uses_today: Mapped[int] = mapped_column(Integer, default=0)
    uses_date: Mapped[date | None] = mapped_column(Date)


class DailyCombo(Base):
    __tablename__ = "daily_combo"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    card_ids: Mapped[list[str]] = mapped_column(JSONB)


class UserCombo(Base):
    __tablename__ = "user_combo"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    found: Mapped[list[str]] = mapped_column(JSONB, default=list)
    claimed: Mapped[bool] = mapped_column(Boolean, default=False)


class Season(Base):
    __tablename__ = "seasons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[int] = mapped_column(Integer, unique=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # "active" | "finished"
    status: Mapped[str] = mapped_column(String(16), default="active")
    results: Mapped[dict | None] = mapped_column(JSONB)


class UserBadge(Base):
    __tablename__ = "user_badges"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    badge_id: Mapped[str] = mapped_column(String(32))
    season_id: Mapped[int | None] = mapped_column(Integer)
    awarded_at: Mapped[datetime] = _now_col()

    __table_args__ = (UniqueConstraint("user_id", "badge_id", "season_id"),)


class AdView(Base):
    __tablename__ = "ad_views"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    provider: Mapped[str] = mapped_column(String(16))
    reward_type: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = _now_col(index=True)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(String(64), index=True)
    props: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _now_col(index=True)
