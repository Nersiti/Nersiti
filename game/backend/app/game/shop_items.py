"""Telegram Stars shop (PLAN.md, section B, "Магазин за Stars").

Prices are in Stars (XTR). Changing a price here changes it everywhere.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

Param = Literal["none", "sector", "color"]


@dataclass(frozen=True)
class ShopItem:
    id: str
    stars: int
    daily_limit: int | None = None
    duration: timedelta | None = None
    param: Param = "none"
    subscription: bool = False
    clan_owner_only: bool = False
    admin_only: bool = False


VIP_PERIOD = timedelta(days=30)
SUBSCRIPTION_PERIOD_SECONDS = 2_592_000  # the only period Telegram allows (30 days)
SHIELD_DURATION = timedelta(hours=8)
COINS_BAG_HOURS = 6
COINS_BAG_MIN = 5000

ITEMS: list[ShopItem] = [
    ShopItem("coins_bag", 50, daily_limit=5),
    ShopItem("energy_refill", 10, daily_limit=10),
    ShopItem("artillery", 75, duration=timedelta(hours=1)),
    ShopItem("shield", 100, duration=SHIELD_DURATION, param="sector"),
    ShopItem("autocollector", 150, duration=timedelta(days=7)),
    ShopItem("vip", 250, duration=VIP_PERIOD, subscription=True),
    ShopItem("clan_color", 300, param="color", clan_owner_only=True),
    ShopItem("clan_promo", 500, duration=timedelta(hours=24), clan_owner_only=True),
    # 1-star item for checking real payments end to end (visible to admins only).
    ShopItem("test_star", 1, admin_only=True),
]

ITEMS_BY_ID: dict[str, ShopItem] = {i.id: i for i in ITEMS}

CLAN_PALETTE = [
    "#ef4444", "#f97316", "#f59e0b", "#eab308", "#84cc16", "#22c55e",
    "#14b8a6", "#06b6d4", "#3b82f6", "#6366f1", "#a855f7", "#ec4899",
]  # fmt: skip
