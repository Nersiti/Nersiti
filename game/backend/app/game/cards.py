"""Upgrade cards (PLAN.md, section B, table of cards)."""

from dataclasses import dataclass
from typing import Literal

from app.game.economy import card_cost, economy_income_gain

Category = Literal["economy", "army", "defense", "boost"]
Effect = Literal["income", "attack_bp", "defense_bp", "multitap", "battery"]


@dataclass(frozen=True)
class Card:
    id: str
    category: Category
    base_cost: int
    growth: float
    effect: Effect
    # income: base coins/hour; *_bp: basis points per level; multitap/battery: per level.
    value: int
    max_level: int = 20

    def cost(self, level_to_buy: int) -> int:
        return card_cost(self.base_cost, self.growth, level_to_buy)

    def gain(self, level_to_buy: int) -> int:
        """Effect added by buying `level_to_buy`."""
        if self.effect == "income":
            return economy_income_gain(self.value, level_to_buy)
        return self.value


CARDS: list[Card] = [
    Card("market", "economy", 100, 1.55, "income", 12),
    Card("workshop", "economy", 400, 1.55, "income", 40),
    Card("factory", "economy", 1_500, 1.55, "income", 130),
    Card("bank", "economy", 6_000, 1.55, "income", 450),
    Card("port", "economy", 25_000, 1.55, "income", 1_600),
    Card("tech_park", "economy", 100_000, 1.55, "income", 5_500),
    Card("barracks", "army", 300, 1.6, "attack_bp", 300),
    Card("range", "army", 3_000, 1.6, "attack_bp", 500),
    Card("air_base", "army", 30_000, 1.6, "attack_bp", 800),
    Card("walls", "defense", 300, 1.6, "defense_bp", 300),
    Card("bunkers", "defense", 3_000, 1.6, "defense_bp", 500),
    Card("air_defense", "defense", 30_000, 1.6, "defense_bp", 800),
    Card("multitap", "boost", 500, 2.0, "multitap", 1, max_level=10),
    Card("battery", "boost", 500, 2.0, "battery", 1, max_level=10),
]

CARDS_BY_ID: dict[str, Card] = {c.id: c for c in CARDS}
