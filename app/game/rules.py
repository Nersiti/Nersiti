"""Game rules: rarities, elements, classes, stats, and value."""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Rarity:
    code: str
    label: str
    emoji: str
    factor: float  # множитель характеристик
    value: int  # базовая ценность (цена захвата) в кристаллах
    color: tuple[int, int, int]
    weight: float  # шанс выпадения для обычного игрока, %
    lord_weight: float  # шанс для Лорда, %


RARITIES: dict[str, Rarity] = {
    r.code: r
    for r in (
        Rarity("common", "Обычная", "⚪", 1.0, 20, (160, 168, 180), 58, 45),
        Rarity("rare", "Редкая", "🔵", 1.2, 50, (70, 150, 255), 27, 32),
        Rarity("epic", "Эпическая", "🟣", 1.45, 120, (175, 90, 255), 11, 16),
        Rarity("legendary", "Легендарная", "🟠", 1.75, 300, (255, 175, 40), 3.5, 6),
        Rarity("mythic", "Мифическая", "🔴", 2.1, 800, (255, 60, 95), 0.5, 1),
    )
}
RARITY_ORDER = list(RARITIES)


@dataclass(frozen=True)
class Element:
    code: str
    label: str
    emoji: str
    color: tuple[int, int, int]


ELEMENTS: dict[str, Element] = {
    e.code: e
    for e in (
        Element("fire", "Огонь", "🔥", (255, 110, 50)),
        Element("water", "Вода", "💧", (60, 160, 255)),
        Element("nature", "Природа", "🌿", (80, 200, 110)),
        Element("lightning", "Молния", "⚡", (245, 215, 60)),
        Element("earth", "Земля", "🪨", (175, 135, 95)),
        Element("dark", "Тьма", "🌑", (140, 95, 190)),
        Element("light", "Свет", "✨", (255, 238, 170)),
    )
}

# Круг стихий: огонь → природа → земля → молния → вода → огонь; свет и тьма сильны друг против друга.
_BEATS = {
    ("fire", "nature"),
    ("nature", "earth"),
    ("earth", "lightning"),
    ("lightning", "water"),
    ("water", "fire"),
    ("light", "dark"),
    ("dark", "light"),
}
ADVANTAGE = 1.3


def element_multiplier(attacker: str, defender: str) -> float:
    return ADVANTAGE if (attacker, defender) in _BEATS else 1.0


@dataclass(frozen=True)
class Klass:
    code: str
    label: str
    perk: str


CLASSES: dict[str, Klass] = {
    k.code: k
    for k in (
        Klass("warrior", "Воин", "атака +20%"),
        Klass("mage", "Маг", "шанс крита 25%"),
        Klass("guardian", "Страж", "защита +30%"),
        Klass("rogue", "Плут", "уклонение 15%"),
        Klass("titan", "Титан", "здоровье +20%"),
        Klass("spirit", "Дух", "лечится 6% здоровья за раунд"),
    )
}

MAX_LEVEL = 20


def roll_rarity(rng: random.Random, lord: bool = False, allowed: list[str] | None = None) -> str:
    codes = allowed or RARITY_ORDER
    weights = [RARITIES[c].lord_weight if lord else RARITIES[c].weight for c in codes]
    return rng.choices(codes, weights=weights, k=1)[0]


def make_stats(atk: float, def_: float, hp: float, rarity: str, rng: random.Random) -> tuple[int, int, int]:
    """LLM gives relative stats 1..10; normalize them to a 15-point budget and scale by rarity."""
    raw = [max(1.0, min(10.0, float(x))) for x in (atk, def_, hp)]
    total = sum(raw)
    norm = [x * 15 / total for x in raw]
    f = RARITIES[rarity].factor
    return (
        round(norm[0] * 8 * f) + rng.randint(0, 3),
        round(norm[1] * 6 * f) + rng.randint(0, 3),
        round(norm[2] * 20 * f) + rng.randint(0, 8),
    )


def card_value(rarity: str, level: int) -> int:
    return round(RARITIES[rarity].value * (1 + 0.1 * (level - 1)))


def xp_for_level(level: int) -> int:
    """Total XP needed to reach ``level``: 2 → 100, 3 → 300, 4 → 600…"""
    return 50 * level * (level - 1)


def level_for_xp(xp: int) -> int:
    level = 1
    while level < MAX_LEVEL and xp >= xp_for_level(level + 1):
        level += 1
    return level


def level_multiplier(level: int) -> float:
    return 1 + 0.05 * (level - 1)


def elo(winner: int, loser: int, k: int = 24) -> int:
    """How many rating points the winner gets (and the loser loses)."""
    expected = 1 / (1 + 10 ** ((loser - winner) / 400))
    return max(1, round(k * (1 - expected)))
