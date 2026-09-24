"""Battle engine: the outcome is computed from stats (fair and reproducible), the LLM only narrates it."""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field

from app.game.rules import ELEMENTS, element_multiplier, level_multiplier
from app.services.llm import LLMClient

log = logging.getLogger(__name__)

MAX_ROUNDS = 12


@dataclass
class Fighter:
    name: str
    word: str
    element: str
    klass: str
    atk: int
    def_: int
    hp: int
    level: int = 1
    ability: str = ""

    def __post_init__(self) -> None:
        m = level_multiplier(self.level)
        self.atk = round(self.atk * m * (1.2 if self.klass == "warrior" else 1))
        self.def_ = round(self.def_ * m * (1.3 if self.klass == "guardian" else 1))
        self.hp = round(self.hp * m * (1.2 if self.klass == "titan" else 1))

    @property
    def crit_chance(self) -> float:
        return 0.25 if self.klass == "mage" else 0.12

    @property
    def dodge_chance(self) -> float:
        return 0.15 if self.klass == "rogue" else 0.06

    @property
    def power(self) -> int:
        return self.atk * 2 + self.def_ + self.hp // 2


@dataclass
class Event:
    round: int
    actor: str  # "a" | "d"
    kind: str  # hit | crit | dodge | ability | heal
    value: int = 0


@dataclass
class BattleResult:
    attacker_won: bool
    rounds: int
    hp_left: tuple[int, int]
    hp_max: tuple[int, int]
    events: list[Event] = field(default_factory=list)


def simulate(a: Fighter, d: Fighter, rng: random.Random) -> BattleResult:
    fighters = {"a": a, "d": d}
    hp = {"a": a.hp, "d": d.hp}
    ability_used = {"a": False, "d": False}
    events: list[Event] = []
    rounds = 0

    for rnd in range(1, MAX_ROUNDS + 1):
        rounds = rnd
        for actor, target in (("a", "d"), ("d", "a")):
            me, enemy = fighters[actor], fighters[target]
            if me.klass == "spirit" and hp[actor] < me.hp:
                heal = max(1, round(me.hp * 0.06))
                hp[actor] = min(me.hp, hp[actor] + heal)
                events.append(Event(rnd, actor, "heal", heal))
            if rng.random() < enemy.dodge_chance:
                events.append(Event(rnd, actor, "dodge"))
                continue
            damage = me.atk * element_multiplier(me.element, enemy.element) * rng.uniform(0.85, 1.15)
            kind = "hit"
            if not ability_used[actor] and hp[actor] < me.hp * 0.4:
                ability_used[actor] = True
                damage *= 1.6
                kind = "ability"
            elif rng.random() < me.crit_chance:
                damage *= 1.6
                kind = "crit"
            dealt = max(max(1, round(me.atk * 0.15)), round(damage - enemy.def_ * 0.5))
            hp[target] -= dealt
            events.append(Event(rnd, actor, kind, dealt))
            if hp[target] <= 0:
                return BattleResult(actor == "a", rounds, (max(hp["a"], 0), max(hp["d"], 0)), (a.hp, d.hp), events)

    attacker_won = hp["a"] / a.hp > hp["d"] / d.hp
    return BattleResult(attacker_won, rounds, (hp["a"], hp["d"]), (a.hp, d.hp), events)


# ---------- рассказ о бое ----------

STORY_PROMPT = """Ты — азартный комментатор боёв в игре «Хозяин Слова», где сражаются существа-слова.
Напиши рассказ о бое на 3–5 предложений (до 550 символов): смешно, динамично, с отсылками к смыслу слов.
Исход уже известен — не меняй его. Без markdown, без заголовков, только текст."""


def _describe(a: Fighter, d: Fighter, result: BattleResult) -> str:
    names = {"a": a.name, "d": d.name}
    lines = [
        f"Атакует: {a.name} (слово «{a.word}», стихия {ELEMENTS[a.element].label}, способность «{a.ability}»).",
        f"Защищается: {d.name} (слово «{d.word}», стихия {ELEMENTS[d.element].label}, способность «{d.ability}»).",
    ]
    for ev in result.events:
        if ev.kind in ("crit", "ability", "dodge"):
            lines.append(f"Раунд {ev.round}: {names[ev.actor]} — {ev.kind} {ev.value or ''}".strip())
    winner = a if result.attacker_won else d
    lines.append(f"Бой длился {result.rounds} раунд(ов). Победил: {winner.name}.")
    return "\n".join(lines)


def fallback_story(a: Fighter, d: Fighter, result: BattleResult) -> str:
    winner, loser = (a, d) if result.attacker_won else (d, a)
    parts = [f"{a.name} бросается на {d.name}!"]
    kinds = {ev.kind for ev in result.events}
    if "ability" in kinds:
        parts.append("В самый отчаянный момент в ход идут способности — искры летят во все стороны.")
    if "crit" in kinds:
        parts.append("Один сокрушительный удар заставляет зрителей ахнуть.")
    if "dodge" in kinds:
        parts.append("Кто-то ловко уворачивается, будто заранее знал, куда бьют.")
    parts.append(f"После {result.rounds}-го раунда {loser.name} сдаётся, а {winner.name} празднует победу.")
    return " ".join(parts)


async def tell_story(llm: LLMClient, a: Fighter, d: Fighter, result: BattleResult, timeout: float = 30.0) -> str:
    try:
        story = await asyncio.wait_for(
            llm.complete(
                [{"role": "system", "content": STORY_PROMPT}, {"role": "user", "content": _describe(a, d, result)}],
                max_tokens=400,
                temperature=0.9,
            ),
            timeout,
        )
    except Exception as e:  # noqa: BLE001 — рассказ не критичен
        log.info("Battle story fallback: %r", e)
        return fallback_story(a, d, result)
    story = story.strip()
    return story[:900] if story else fallback_story(a, d, result)
