"""Share cards: public signed image URLs, story and chat sharing."""

import hashlib
import hmac
import re
import time
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.game import clan_service, world_service
from app.game.errors import GameError
from app.i18n import pick_lang, t
from app.images.share_card import CardText, render
from app.models import City, Clan, User

KINDS = ("me", "clan")
FORMATS = ("story", "post")
CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cards"
CACHE_SECONDS = 600
NAME_RE = re.compile(r"^(\d{1,20})-(me|clan)-(story|post)-([0-9a-f]{20})\.png$")


def _sig(user_id: int, kind: str, fmt: str) -> str:
    key = get_settings().webhook_secret.encode()
    return hmac.new(key, f"{user_id}:{kind}:{fmt}".encode(), hashlib.sha256).hexdigest()[:20]


def image_url(user_id: int, kind: str, fmt: str) -> str:
    name = f"{user_id}-{kind}-{fmt}-{_sig(user_id, kind, fmt)}.png"
    return f"https://{get_settings().domain}/api/share/img/{name}"


def parse_name(name: str) -> tuple[int, str, str]:
    m = NAME_RE.match(name)
    if not m:
        raise GameError("not_found", 404)
    user_id, kind, fmt, sig = int(m.group(1)), m.group(2), m.group(3), m.group(4)
    if not hmac.compare_digest(sig, _sig(user_id, kind, fmt)):
        raise GameError("not_found", 404)
    return user_id, kind, fmt


async def share_link(session: AsyncSession, user: User, kind: str) -> str:
    bot = get_settings().bot_username
    if kind == "clan" and user.clan_id:
        clan = await session.get(Clan, user.clan_id)
        if clan is not None and clan.kind != clan_service.MILITIA:
            return clan_service.start_link(bot, clan.id)
    return f"https://t.me/{bot}?startapp=r_{user.id}"


async def card_text(session: AsyncSession, user: User, kind: str) -> CardText:
    lang = pick_lang(user.language_code)
    settings = get_settings()
    city = await session.get(City, user.city_id) if user.city_id else None
    clan = await session.get(Clan, user.clan_id) if user.clan_id else None
    city_name = world_service.city_name(city, lang) if city else "?"
    clan_title = await clan_service.display_title(session, clan, lang) if clan else "—"
    held = await clan_service.sectors_held(session, clan.id) if clan else 0
    rank = await clan_service.clan_rank(session, clan) if clan else 0
    footer = f"t.me/{settings.bot_username}"
    color = clan.color if clan else "#3d8bfd"
    if kind == "clan" and clan is not None:
        return CardText(
            title=clan_title,
            lines=[t(lang, "share.clan.line", city=city_name)],
            stats=[
                (f"#{rank}", t(lang, "share.stat.rank")),
                (str(held), t(lang, "share.stat.sectors")),
                (str(clan.members_count), t(lang, "share.stat.members")),
            ],
            cta=t(lang, "share.clan.cta"),
            footer=footer,
            color=color,
            brand=settings.game_name,
        )
    return CardText(
        title=user.first_name or "Player",
        lines=[t(lang, "share.me.city", city=city_name), t(lang, "share.me.clan", clan=clan_title)],
        stats=[
            (f"#{rank}", t(lang, "share.stat.rank")),
            (str(held), t(lang, "share.stat.sectors")),
            (str(user.level), t(lang, "share.stat.level")),
        ],
        cta=t(lang, "share.me.cta"),
        footer=footer,
        color=color,
        brand=settings.game_name,
    )


async def render_cached(session: AsyncSession, user: User, kind: str, fmt: str) -> bytes:
    path = CACHE_DIR / f"{user.id}-{kind}-{fmt}.png"
    if path.exists() and time.time() - path.stat().st_mtime < CACHE_SECONDS:
        return path.read_bytes()
    data = render(await card_text(session, user, kind), fmt)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    return data
