"""Rendering the card image: art from the GPU + frame, rarity, stats. Pure Pillow, no network."""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from app.game.rules import CLASSES, ELEMENTS, RARITIES

log = logging.getLogger(__name__)

W, H = 768, 1075
ART_BOX = (34, 150, 734, 640)  # 700 × 490
FONTS_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
BG = (16, 17, 26)
PANEL = (28, 30, 44)
TEXT = (238, 240, 248)
MUTED = (150, 156, 175)


@dataclass(frozen=True)
class CardView:
    word: str
    name: str
    title: str
    element: str
    klass: str
    rarity: str
    atk: int
    def_: int
    hp: int
    ability: str
    ability_text: str
    number: int
    creator: str
    bot_username: str = ""


@lru_cache(maxsize=64)
def font(kind: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    files = {"serif": "DejaVuSerif-Bold.ttf", "bold": "DejaVuSans-Bold.ttf", "regular": "DejaVuSans.ttf"}
    try:
        return ImageFont.truetype(str(FONTS_DIR / files[kind]), size)
    except OSError:
        log.warning("Font %s not found, using default", files[kind])
        return ImageFont.load_default(size)


def _fit_font(draw: ImageDraw.ImageDraw, text: str, kind: str, size: int, max_width: int, min_size: int = 18):
    while size > min_size and draw.textlength(text, font=font(kind, size)) > max_width:
        size -= 2
    return font(kind, size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, fnt, max_width: int, max_lines: int) -> list[str]:  # type: ignore[no-untyped-def]
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=fnt) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
        if len(lines) == max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines and " ".join(lines) != text.strip():
        last = lines[-1]
        while last and draw.textlength(last + "…", font=fnt) > max_width:
            last = last[:-1]
        lines[-1] = last.rstrip() + "…"
    return lines


def _gradient(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    w, h = size
    column = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(h - 1, 1)
        column.putpixel((0, y), tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return column.resize((w, h))


def _placeholder_art(color: tuple[int, int, int], size: tuple[int, int]) -> Image.Image:
    dark = tuple(c // 5 for c in color)
    return _gradient(size, color, dark)  # type: ignore[arg-type]


def _rainbow_overlay(size: tuple[int, int]) -> Image.Image:
    colors = [(255, 80, 80), (255, 200, 60), (80, 255, 140), (60, 170, 255), (200, 90, 255)]
    w, h = size
    band = Image.new("RGB", (len(colors), 1))
    for i, c in enumerate(colors):
        band.putpixel((i, 0), c)
    return band.resize((w * 2, h), Image.BILINEAR).rotate(25, expand=False).crop((0, 0, w, h))


def render_card(view: CardView, art: bytes | None) -> bytes:
    rarity = RARITIES[view.rarity]
    element = ELEMENTS[view.element]
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # рамка цвета редкости с мягким свечением
    glow = Image.new("RGB", (W, H), BG)
    ImageDraw.Draw(glow).rounded_rectangle((6, 6, W - 7, H - 7), radius=34, outline=rarity.color, width=14)
    img = Image.blend(img, glow.filter(ImageFilter.GaussianBlur(10)), 0.9)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((10, 10, W - 11, H - 11), radius=30, outline=rarity.color, width=6)
    draw.rounded_rectangle((20, 20, W - 21, H - 21), radius=24, fill=BG)

    # заголовок: само слово — главное на карте
    pill_text = element.label.upper()
    pill_font = font("bold", 20)
    pill_w = int(draw.textlength(pill_text, font=pill_font)) + 32
    word_font = _fit_font(draw, f"«{view.word}»", "serif", 50, W - 110 - pill_w)
    draw.text((40, 88), f"«{view.word}»", font=word_font, fill=TEXT, anchor="lm")
    draw.rounded_rectangle((W - 40 - pill_w, 68, W - 40, 108), radius=20, fill=element.color)
    draw.text((W - 40 - pill_w // 2, 88), pill_text, font=pill_font, fill=(20, 20, 28), anchor="mm")
    draw.text((40, 128), f"№{view.number}", font=font("regular", 18), fill=MUTED, anchor="lm")

    # арт
    box_w, box_h = ART_BOX[2] - ART_BOX[0], ART_BOX[3] - ART_BOX[1]
    picture: Image.Image | None = None
    if art:
        try:
            picture = ImageOps.fit(Image.open(io.BytesIO(art)).convert("RGB"), (box_w, box_h), Image.LANCZOS)
        except Exception as e:  # noqa: BLE001 — битая картинка не должна ломать карту
            log.warning("Bad art image: %r", e)
    if picture is None:
        picture = _placeholder_art(element.color, (box_w, box_h))
    mask = Image.new("L", (box_w, box_h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, box_w - 1, box_h - 1), radius=18, fill=255)
    img.paste(picture, ART_BOX[:2], mask)
    draw.rounded_rectangle(ART_BOX, radius=18, outline=rarity.color, width=4)

    # лента редкости
    ribbon = f"{rarity.label.upper()} · {CLASSES[view.klass].label.upper()}"
    draw.rounded_rectangle((34, 652, 734, 698), radius=14, fill=rarity.color)
    draw.text((W // 2, 675), ribbon, font=font("bold", 24), fill=(18, 18, 26), anchor="mm")

    # имя существа
    name_line = f"{view.name} — {view.title}" if view.title else view.name
    draw.text((W // 2, 730), name_line, font=_fit_font(draw, name_line, "bold", 30, W - 90), fill=TEXT, anchor="mm")

    # способность
    draw.rounded_rectangle((34, 758, 734, 902), radius=16, fill=PANEL)
    draw.text((56, 784), f"✦ {view.ability}", font=_fit_font(draw, f"✦ {view.ability}", "bold", 24, 650), fill=rarity.color, anchor="lm")
    body_font = font("regular", 21)
    for i, line in enumerate(_wrap(draw, view.ability_text, body_font, 650, 3)):
        draw.text((56, 818 + i * 27), line, font=body_font, fill=TEXT)

    # характеристики
    stats = (("АТАКА", view.atk, (255, 110, 90)), ("ЗАЩИТА", view.def_, (90, 170, 255)), ("ЗДОРОВЬЕ", view.hp, (90, 220, 130)))
    for i, (label, value, color) in enumerate(stats):
        x0 = 34 + i * 238
        draw.rounded_rectangle((x0, 916, x0 + 224, 1000), radius=16, fill=PANEL, outline=color, width=3)
        draw.text((x0 + 112, 942), label, font=font("bold", 18), fill=MUTED, anchor="mm")
        draw.text((x0 + 112, 975), str(value), font=font("serif", 34), fill=color, anchor="mm")

    # подвал
    footer = f"Открыл: {view.creator}"
    if view.bot_username:
        footer += f"   ·   @{view.bot_username}"
    draw.text((W // 2, 1030), footer, font=_fit_font(draw, footer, "regular", 20, W - 80, 14), fill=MUTED, anchor="mm")

    if view.rarity == "mythic":
        img = Image.blend(img, _rainbow_overlay((W, H)), 0.16)

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90, optimize=True)
    return out.getvalue()
