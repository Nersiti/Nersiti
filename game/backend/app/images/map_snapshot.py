"""Hourly world snapshot (for the end-of-season timelapse).

Equirectangular projection: every playable city is a dot; cities controlled by a clan
are drawn bigger in the clan's color.
"""

import io
import math
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import City, Clan

WIDTH, HEIGHT = 2048, 1024
SNAPSHOT_DIR = Path(__file__).resolve().parents[2] / "data" / "snapshots"
BACKGROUND = (10, 14, 26)
NEUTRAL = (70, 78, 96)


def _xy(lat: float, lng: float) -> tuple[float, float]:
    return (lng + 180) / 360 * WIDTH, (90 - lat) / 180 * HEIGHT


def _rgb(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


async def render_snapshot(session: AsyncSession) -> bytes:
    cities = (
        await session.execute(
            select(City.lat, City.lng, City.population, City.controller_clan_id).where(
                City.sectors_count > 0
            )
        )
    ).all()
    colors = {
        cid: _rgb(color)
        for cid, color in (await session.execute(select(Clan.id, Clan.color))).all()
    }
    img = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(img)
    for lat, lng, _pop, controller in cities:
        if controller is None:
            x, y = _xy(lat, lng)
            draw.point((x, y), fill=NEUTRAL)
    for lat, lng, pop, controller in cities:
        if controller is not None:
            x, y = _xy(lat, lng)
            r = 1.5 + math.log10(max(pop, 15_000) / 15_000 + 1) * 2.5
            draw.ellipse([x - r, y - r, x + r, y + r], fill=colors.get(controller, NEUTRAL))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


async def save_snapshot(session: AsyncSession, season_number: int, now: datetime) -> Path:
    folder = SNAPSHOT_DIR / f"season_{season_number}"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{now:%Y%m%d%H}.png"
    path.write_bytes(await render_snapshot(session))
    return path
