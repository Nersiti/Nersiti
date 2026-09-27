"""Share cards (PNG) for stories and chat messages, rendered with Pillow."""

import io
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT_DIRS = [Path("/usr/share/fonts/truetype/dejavu"), Path("/usr/share/fonts/dejavu")]
SIZES = {"story": (1080, 1920), "post": (1200, 630)}


@dataclass
class CardText:
    title: str  # big line: player or clan name
    lines: list[str]  # smaller lines under the title
    stats: list[tuple[str, str]]  # (value, label)
    cta: str
    footer: str
    color: str  # clan color, "#rrggbb"
    brand: str


@lru_cache(maxsize=32)
def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for d in FONT_DIRS:
        if (d / name).exists():
            return ImageFont.truetype(str(d / name), size)
    return ImageFont.load_default(size=size)


def _rgb(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    try:
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except (ValueError, IndexError):
        return 61, 139, 253


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b, strict=True))


def _fit(draw: ImageDraw.ImageDraw, text: str, max_width: int, size: int, min_size: int = 28):
    while size > min_size:
        font = _font(size)
        if draw.textlength(text, font=font) <= max_width:
            return font
        size -= 4
    font = _font(min_size)
    while text and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1]
    return font


def _hexagon(cx: float, cy: float, r: float) -> list[tuple[float, float]]:
    return [
        (cx + r * math.cos(math.radians(60 * i + 30)), cy + r * math.sin(math.radians(60 * i + 30)))
        for i in range(6)
    ]


def render(card: CardText, fmt: str = "story") -> bytes:
    width, height = SIZES[fmt]
    story = fmt == "story"
    base = _rgb(card.color)
    top, bottom = _mix(base, (10, 14, 30), 0.35), (8, 11, 24)

    img = Image.new("RGB", (width, height), bottom)
    draw = ImageDraw.Draw(img)
    for y in range(height):
        draw.line([(0, y), (width, y)], fill=_mix(top, bottom, y / height))

    # Decorative hex grid in the clan color.
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    r = width / (9 if story else 14)
    for row in range(-1, int(height / (r * 1.5)) + 2):
        for col in range(-1, int(width / (r * 1.73)) + 2):
            cx = col * r * 1.732 + (r * 0.866 if row % 2 else 0)
            cy = row * r * 1.5
            fade = max(0.0, 1 - cy / (height * 0.85))
            alpha = int(40 * fade) if (row * 7 + col * 3) % 5 else int(110 * fade)
            odraw.polygon(
                _hexagon(cx, cy, r * 0.93), outline=(*base, alpha + 20), fill=(*base, alpha // 3)
            )
    img.paste(overlay, (0, 0), overlay)
    draw = ImageDraw.Draw(img)

    pad = 80 if story else 60
    y = int(height * (0.34 if story else 0.14))
    white, hint = (255, 255, 255), (190, 198, 214)

    brand_font = _font(44 if story else 30)
    draw.text((pad, int(height * 0.06)), card.brand.upper(), font=brand_font, fill=white)

    title_font = _fit(draw, card.title, width - 2 * pad, 112 if story else 72)
    draw.text((pad, y), card.title, font=title_font, fill=white)
    y += title_font.size + (40 if story else 20)

    for line in card.lines:
        font = _fit(draw, line, width - 2 * pad, 54 if story else 34, 24)
        draw.text((pad, y), line, font=font, fill=hint)
        y += font.size + (22 if story else 12)

    if card.stats:
        y += 40 if story else 16
        col_w = (width - 2 * pad) / len(card.stats)
        for i, (value, label) in enumerate(card.stats):
            x = pad + i * col_w
            vfont = _fit(draw, value, int(col_w) - 20, 84 if story else 52, 28)
            draw.text((x, y), value, font=vfont, fill=_mix(base, white, 0.45))
            draw.text(
                (x, y + vfont.size + 10),
                label,
                font=_font(34 if story else 22, bold=False),
                fill=hint,
            )

    cta_font = _fit(draw, card.cta, width - 2 * pad, 60 if story else 36, 24)
    box_h = cta_font.size + (70 if story else 40)
    box_y = int(height * (0.80 if story else 0.70))
    draw.rounded_rectangle([pad, box_y, width - pad, box_y + box_h], radius=box_h // 2, fill=base)
    tw = draw.textlength(card.cta, font=cta_font)
    draw.text(
        ((width - tw) / 2, box_y + (box_h - cta_font.size) / 2 - 4),
        card.cta,
        font=cta_font,
        fill=white,
    )

    foot_font = _font(36 if story else 24, bold=False)
    fw = draw.textlength(card.footer, font=foot_font)
    draw.text(
        ((width - fw) / 2, box_y + box_h + (40 if story else 18)),
        card.footer,
        font=foot_font,
        fill=hint,
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
