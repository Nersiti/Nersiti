import colorsys
import logging
import re
from datetime import datetime, timedelta

from aiogram.exceptions import TelegramAPIError
from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.instance import get_bot
from app.game import world_service
from app.game.errors import GameError
from app.i18n import t
from app.models import City, Clan, Sector, User
from app.redis_client import get_redis

log = logging.getLogger(__name__)

MILITIA = "militia"
CHANNEL = "channel"
GROUP = "group"
CLAN_SWITCH_COOLDOWN = timedelta(hours=24)
MIN_MEMBERS = {CHANNEL: 10, GROUP: 3}
SUB_CACHE_OK_SECONDS = 24 * 3600
SUB_CACHE_FAIL_SECONDS = 30
CLAN_RE = re.compile(r"^c_(\d{1,10})$")


def parse_clan_param(start_param: str | None) -> int | None:
    m = CLAN_RE.match(start_param or "")
    return int(m.group(1)) if m else None


def clan_color(clan_id: int) -> str:
    """Distinct, deterministic colors: golden-angle hue steps."""
    hue = (clan_id * 137.508) % 360 / 360
    r, g, b = colorsys.hls_to_rgb(hue, 0.55, 0.7)
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


def start_link(bot_username: str, clan_id: int) -> str:
    return f"https://t.me/{bot_username}?startapp=c_{clan_id}"


def subscribe_url(clan: Clan) -> str | None:
    if clan.username:
        return f"https://t.me/{clan.username}"
    return clan.invite_link


async def display_title(session: AsyncSession, clan: Clan, lang: str) -> str:
    if clan.kind != MILITIA:
        return clan.title
    city = await session.get(City, clan.city_id) if clan.city_id else None
    return t(lang, "clan.militia", city=world_service.city_name(city, lang) if city else clan.title)


async def clan_summary(session: AsyncSession, clan: Clan, lang: str) -> dict:
    return {
        "id": clan.id,
        "title": await display_title(session, clan, lang),
        "kind": clan.kind,
        "is_militia": clan.kind == MILITIA,
        "color": clan.color,
        "members_count": clan.members_count,
        "season_points": clan.season_points,
        "username": clan.username,
        "subscribers_only": clan.subscribers_only,
        "subscribe_url": subscribe_url(clan) if clan.subscribers_only else None,
        "city_id": clan.city_id,
    }


async def sectors_held(session: AsyncSession, clan_id: int) -> int:
    return (
        await session.execute(
            select(func.count()).select_from(Sector).where(Sector.owner_clan_id == clan_id)
        )
    ).scalar_one()


async def clan_rank(session: AsyncSession, clan: Clan) -> int:
    better = (
        await session.execute(
            select(func.count())
            .select_from(Clan)
            .where(Clan.season_points > clan.season_points, Clan.banned.is_(False))
        )
    ).scalar_one()
    return better + 1


async def get_or_create_militia(session: AsyncSession, city: City) -> Clan:
    stmt = select(Clan).where(Clan.kind == MILITIA, Clan.city_id == city.id)
    clan = (await session.execute(stmt)).scalar_one_or_none()
    if clan is not None:
        return clan
    await session.execute(
        insert(Clan)
        .values(kind=MILITIA, city_id=city.id, title=city.name_en, color="#888888")
        .on_conflict_do_nothing(index_elements=["city_id"], index_where=text("kind = 'militia'"))
    )
    clan = (await session.execute(stmt)).scalar_one()
    if clan.color == "#888888":
        clan.color = clan_color(clan.id)
    return clan


async def _move_member(session: AsyncSession, user: User, clan: Clan, now: datetime) -> None:
    if user.clan_id == clan.id:
        return
    if user.clan_id is not None:
        await session.execute(
            update(Clan)
            .where(Clan.id == user.clan_id)
            .values(members_count=func.greatest(Clan.members_count - 1, 0))
        )
    await session.execute(
        update(Clan).where(Clan.id == clan.id).values(members_count=Clan.members_count + 1)
    )
    user.clan_id = clan.id
    if clan.kind != MILITIA:
        user.clan_joined_at = now
    await session.refresh(clan, ["members_count"])


async def join_militia(session: AsyncSession, user: User, now: datetime) -> Clan:
    city = await session.get(City, user.city_id)
    if city is None:
        raise GameError("onboarding_required")
    clan = await get_or_create_militia(session, city)
    await _move_member(session, user, clan, now)
    return clan


async def is_subscribed(chat_id: int, user_id: int) -> bool:
    """Checks channel/group membership through the Bot API (cached in Redis)."""
    redis = get_redis()
    key = f"sub:{chat_id}:{user_id}"
    cached = await redis.get(key)
    if cached is not None:
        return cached == "1"
    member = await get_bot().get_chat_member(chat_id=chat_id, user_id=user_id)
    ok = member.status in ("creator", "administrator", "member") or (
        member.status == "restricted" and bool(getattr(member, "is_member", False))
    )
    await redis.set(
        key, "1" if ok else "0", ex=SUB_CACHE_OK_SECONDS if ok else SUB_CACHE_FAIL_SECONDS
    )
    return ok


async def join_clan(session: AsyncSession, user: User, clan_id: int, now: datetime) -> Clan:
    if user.city_id is None:
        raise GameError("onboarding_required")
    clan = await session.get(Clan, clan_id)
    if clan is None or clan.banned:
        raise GameError("clan_not_found", 404)
    if clan.id == user.clan_id:
        return clan
    if clan.kind == MILITIA:
        if clan.city_id != user.city_id:
            raise GameError("foreign_militia", 403)
        await _move_member(session, user, clan, now)
        return clan
    if user.clan_joined_at is not None and now - user.clan_joined_at < CLAN_SWITCH_COOLDOWN:
        raise GameError("clan_cooldown", 409)
    if clan.subscribers_only and clan.tg_chat_id is not None:
        try:
            subscribed = await is_subscribed(clan.tg_chat_id, user.id)
        except TelegramAPIError as exc:
            log.warning("Subscription check failed for clan %s: %s", clan.id, exc)
            raise GameError("subscription_check_failed", 503) from exc
        if not subscribed:
            raise GameError("subscribe_required", 403)
    await _move_member(session, user, clan, now)
    return clan


async def recheck_subscription(session: AsyncSession, user: User, now: datetime) -> bool:
    """Moves the user to the militia if they left a subscribers-only channel.

    At most one Bot API call per user per day; errors are ignored. Returns True if moved.
    """
    if user.clan_id is None or user.city_id is None:
        return False
    clan = await session.get(Clan, user.clan_id)
    if clan is None or not clan.subscribers_only or clan.tg_chat_id is None:
        return False
    redis = get_redis()
    if not await redis.set(f"subchk:{user.id}:{clan.id}", "1", ex=SUB_CACHE_OK_SECONDS, nx=True):
        return False
    try:
        if await is_subscribed(clan.tg_chat_id, user.id):
            return False
    except TelegramAPIError:
        return False
    await join_militia(session, user, now)
    return True


async def upsert_chat_clan(
    session: AsyncSession,
    *,
    kind: str,
    chat_id: int,
    title: str,
    username: str | None,
    owner_user_id: int,
) -> tuple[Clan, bool]:
    clan = (
        await session.execute(select(Clan).where(Clan.tg_chat_id == chat_id))
    ).scalar_one_or_none()
    if clan is not None:
        clan.title = title[:128]
        clan.username = username
        clan.owner_user_id = owner_user_id
        clan.kind = kind
        return clan, False
    clan = Clan(
        kind=kind,
        tg_chat_id=chat_id,
        title=title[:128],
        username=username,
        owner_user_id=owner_user_id,
        members_count=0,
    )
    session.add(clan)
    await session.flush()
    clan.color = clan_color(clan.id)
    return clan, True
