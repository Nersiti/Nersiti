"""Turning a word into a creature: the LLM invents it, and a fallback kicks in if the model is unavailable."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import re
from dataclasses import dataclass

from app.game.rules import CLASSES, ELEMENTS
from app.services.llm import LLMClient
from app.services.moderation import is_prompt_allowed

log = logging.getLogger(__name__)

GENESIS_PROMPT = """Ты — геймдизайнер коллекционной карточной игры «Хозяин Слова».
Игрок присылает слово или короткую фразу, а ты превращаешь её в существо для карты.
Существо должно остроумно и узнаваемо воплощать смысл слова — игроку должно быть смешно и хотеться показать карту друзьям.
Характеристики отражают смысл: у «понедельника» огромное здоровье, у «кофе» — атака, у «бабушки» — защита.

Верни ТОЛЬКО JSON без пояснений:
{"allowed": true,
 "name": "имя существа, до 24 символов",
 "title": "прозвище, до 28 символов",
 "element": "fire|water|nature|lightning|earth|dark|light",
 "class": "warrior|mage|guardian|rogue|titan|spirit",
 "atk": 1-10, "def": 1-10, "hp": 1-10,
 "ability": "название способности, до 24 символов",
 "ability_text": "что делает способность, остроумно, до 110 символов",
 "lore": "история существа, смешно, до 170 символов",
 "art": "English prompt for the card illustration: describe the creature, its appearance, pose, background. No text. Up to 45 words."}

Пример для слова «будильник»:
{"allowed": true, "name": "Звонарь Рассвета", "title": "Враг сладкого сна", "element": "lightning", "class": "rogue",
 "atk": 8, "def": 3, "hp": 5, "ability": "Ещё пять минут",
 "ability_text": "Противник засыпает на ход и просыпается уже опоздавшим.",
 "lore": "Живёт на тумбочке и питается чужими снами. Боится только севшей батарейки.",
 "art": "mischievous little creature made of an old brass alarm clock, bells as horns, crackling blue sparks, cozy bedroom at dawn"}

Обычные имена и ники (Анна, Макс, Котик2007) разрешены. Бренды и названия вещей разрешены.
Если слово — имя или фамилия конкретного известного человека (политика, знаменитости), политическая партия или лозунг,
оскорбление религии или национальности, мат, 18+, наркотики, экстремизм или насилие над людьми —
верни {"allowed": false, "reason": "кратко почему"}."""

_JSON = re.compile(r"\{.*\}", re.S)
_TRAILING_COMMA = re.compile(r",\s*([}\]])")

_TITLES = ("Неудержимый", "Древний", "Коварный", "Великолепный", "Вечный", "Загадочный", "Грозный", "Хитроумный")
_ABILITIES = (
    ("Внезапность", "Появляется, когда его совсем не ждут, и наносит двойной удар."),
    ("Упрямство", "Отказывается проигрывать, пока у противника не кончится терпение."),
    ("Хаос", "Путает все планы врага. Иногда и свои."),
    ("Обаяние", "Противник так очарован, что забывает атаковать."),
)


@dataclass
class CreatureDraft:
    name: str
    title: str
    element: str
    klass: str
    atk: float
    def_: float
    hp: float
    ability: str
    ability_text: str
    lore: str
    art: str


class NotAllowed(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _cut(value: object, limit: int, default: str = "") -> str:
    text = str(value or "").strip().strip('"').strip()
    return (text or default)[:limit]


def _num(value: object, default: float = 5.0) -> float:
    try:
        return max(1.0, min(10.0, float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def parse_draft(raw: str, word: str) -> CreatureDraft:
    """Parse the model's response. Raises NotAllowed or ValueError."""
    match = _JSON.search(raw.replace("```json", "").replace("```", ""))
    if not match:
        raise ValueError("no JSON in LLM answer")
    chunk = match.group(0)
    try:
        data = json.loads(chunk)
    except ValueError:
        data = json.loads(_TRAILING_COMMA.sub(r"\1", chunk))  # маленькие модели любят лишние запятые
    if not isinstance(data, dict):
        raise ValueError("LLM JSON is not an object")
    if data.get("allowed") is False:
        raise NotAllowed(_cut(data.get("reason"), 200, "запрещённая тема"))
    element = str(data.get("element", "")).lower()
    klass = str(data.get("class", "")).lower()
    fallback = fallback_draft(word)
    return CreatureDraft(
        name=_cut(data.get("name"), 32, fallback.name),
        title=_cut(data.get("title"), 40, fallback.title),
        element=element if element in ELEMENTS else fallback.element,
        klass=klass if klass in CLASSES else fallback.klass,
        atk=_num(data.get("atk")),
        def_=_num(data.get("def")),
        hp=_num(data.get("hp")),
        ability=_cut(data.get("ability"), 40, fallback.ability),
        ability_text=_cut(data.get("ability_text"), 160, fallback.ability_text),
        lore=_cut(data.get("lore"), 260, fallback.lore),
        art=_cut(data.get("art"), 400, fallback.art),
    )


def fallback_draft(word: str) -> CreatureDraft:
    """A creature without an LLM: deterministic by word, so it's stable."""
    rng = random.Random(int(hashlib.sha256(word.encode()).hexdigest(), 16))
    ability, ability_text = rng.choice(_ABILITIES)
    name = word[:1].upper() + word[1:]
    return CreatureDraft(
        name=name[:32],
        title=rng.choice(_TITLES),
        element=rng.choice(list(ELEMENTS)),
        klass=rng.choice(list(CLASSES)),
        atk=rng.randint(2, 9),
        def_=rng.randint(2, 9),
        hp=rng.randint(2, 9),
        ability=ability,
        ability_text=ability_text,
        lore=f"Родилось из слова «{word}» в тот миг, когда кто-то впервые произнёс его вслух.",
        art=f"a fantasy creature that embodies the concept of '{word}', mysterious glowing aura, epic pose",
    )


async def invent_creature(llm: LLMClient, word: str, timeout: float = 60.0) -> CreatureDraft:
    """Ask the LLM for a creature. NotAllowed propagates; any other error falls back to the stub."""
    try:
        raw = await asyncio.wait_for(
            llm.complete(
                [{"role": "system", "content": GENESIS_PROMPT}, {"role": "user", "content": word}],
                max_tokens=600,
                temperature=0.9,
            ),
            timeout,
        )
        if not raw.strip():  # нейросеть не подключена (LLM_BACKEND=mock)
            return fallback_draft(word)
        draft = parse_draft(raw, word)
        texts = " ".join((draft.name, draft.title, draft.ability, draft.ability_text, draft.lore))
        if not is_prompt_allowed(texts) or not is_prompt_allowed(draft.art):
            log.warning("LLM produced unsafe text for %r, using fallback", word)
            return fallback_draft(word)
        return draft
    except NotAllowed:
        raise
    except Exception as e:  # noqa: BLE001 — игра должна работать и без LLM
        log.warning("Creature generation fell back for %r: %r", word, e)
        return fallback_draft(word)
