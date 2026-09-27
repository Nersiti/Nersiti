"""World generation: cities -> H3 sectors (PLAN.md, section B, "Мир").

Pure functions, no IO: used by scripts/build_world.py and unit tests.
"""

import difflib
import re
from dataclasses import dataclass

import h3

H3_RES = 6
CAPITAL_CENTER_VALUE = 5
CITY_CENTER_VALUE = 3
MILLION_RING1_VALUE = 2
DEFAULT_VALUE = 1


def ring_k(population: int) -> int:
    if population < 100_000:
        return 1
    if population < 500_000:
        return 2
    if population < 1_000_000:
        return 3
    if population < 5_000_000:
        return 4
    return 5


@dataclass
class CityIn:
    id: int
    name_en: str
    name_ru: str | None
    country_code: str
    lat: float
    lng: float
    population: int
    is_capital: bool = False
    # First-level admin division (region). Used to merge city districts into the city.
    admin1: str = ""
    sectors_count: int = 0


@dataclass(frozen=True)
class SectorOut:
    h3: str
    city_id: int
    lat: float
    lng: float
    value: int


def generate_sectors(cities: list[CityIn]) -> tuple[list[CityIn], list[SectorOut]]:
    """Returns (cities that got their own center sector, all sectors).

    Pass 1 (descending population): a city is merged into a bigger one when its
    center cell is the bigger city's center, or lies inside the bigger city's ring
    and both are in the same region (GeoNames lists districts such as Moscow's
    "Mar'ino" as separate places). Otherwise it claims its center cell.
    Pass 2: rings are handed out in descending population order, already claimed
    cells are skipped.
    """
    ordered = sorted(cities, key=lambda c: (-c.population, c.id))
    owner: dict[str, int] = {}
    centers: dict[int, str] = {}
    ring_of: dict[str, CityIn] = {}  # cell -> biggest kept city whose ring covers it
    kept: list[CityIn] = []

    for city in ordered:
        cell = h3.latlng_to_cell(city.lat, city.lng, H3_RES)
        if cell in owner:
            continue
        bigger = ring_of.get(cell)
        if (
            bigger is not None
            and bigger.country_code == city.country_code
            and bigger.admin1 == city.admin1
        ):
            continue
        owner[cell] = city.id
        centers[city.id] = cell
        kept.append(city)
        for ring_cell in h3.grid_disk(cell, ring_k(city.population)):
            ring_of.setdefault(ring_cell, city)

    for city in kept:
        for cell in h3.grid_disk(centers[city.id], ring_k(city.population)):
            owner.setdefault(cell, city.id)

    by_id = {c.id: c for c in kept}
    sectors: list[SectorOut] = []
    for cell, city_id in owner.items():
        city = by_id[city_id]
        center = centers[city_id]
        if cell == center:
            value = CAPITAL_CENTER_VALUE if city.is_capital else CITY_CENTER_VALUE
        elif city.population >= 1_000_000 and h3.grid_distance(center, cell) == 1:
            value = MILLION_RING1_VALUE
        else:
            value = DEFAULT_VALUE
        lat, lng = h3.cell_to_latlng(cell)
        sectors.append(SectorOut(cell, city_id, round(lat, 6), round(lng, 6), value))
        city.sectors_count += 1

    return kept, sectors


# --- Russian names fallback (used only when GeoNames alternateNamesV2 is unavailable) ---

_RU_LETTERS = set("абвгдеёжзийклмнопрстуфхцчшщъыьэюя")
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu",
    "я": "ya",
}  # fmt: skip
_LATIN_RE = re.compile(r"^[A-Za-z][A-Za-z '\-’.]*$")


def _is_russian_spelling(name: str) -> bool:
    low = name.lower()
    return any(ch in _RU_LETTERS for ch in low) and all(
        ch in _RU_LETTERS or ch in " -'’." for ch in low
    )


def _looks_non_russian(name: str) -> bool:
    low = name.lower()
    # Pre-reform / Church Slavonic ("Лондонъ"), Ukrainian ("Корольов", "Хабаровськ")
    # and Belarusian-style ("Митишчи") spellings.
    return any(p in low for p in ("ъ", "ськ", "цьк", "ьо", "шч"))


def guess_ru_name(name_en: str, alternatenames: list[str]) -> str | None:
    candidates = {a for a in alternatenames if _is_russian_spelling(a)}
    if not candidates:
        return None
    preferred = {c for c in candidates if not _looks_non_russian(c)}
    candidates = preferred or candidates
    latins = [name_en] + [a for a in alternatenames if _LATIN_RE.match(a)]

    best_key: tuple | None = None
    best: str | None = None
    for cand in sorted(candidates):
        translit = "".join(_TRANSLIT.get(ch, ch) for ch in cand.lower())
        ratios = [difflib.SequenceMatcher(None, translit, x.lower()).ratio() for x in latins]
        key = (round(max(ratios), 3), sum(r >= 0.8 for r in ratios), "-" in cand, len(cand))
        if best_key is None or key > best_key:
            best_key, best = key, cand
    return best
