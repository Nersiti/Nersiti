"""Каталог товаров. Цены меняются здесь."""

from __future__ import annotations

from dataclasses import dataclass

# Telegram поддерживает подписки за Stars только с периодом 30 дней.
SUBSCRIPTION_PERIOD = 30 * 24 * 60 * 60


@dataclass(frozen=True)
class Product:
    code: str
    title: str  # до 32 символов — ограничение Telegram для счёта
    description: str  # до 255 символов
    stars: int
    rub: int  # целые рубли
    crystals: int = 0
    premium_days: int = 0  # статус «Лорд»
    subscription: bool = False  # при оплате звёздами — автопродление каждые 30 дней
    ref_value: int = 0  # база для реферальной комиссии (в кристаллах)
    badge: str = ""

    @property
    def is_premium(self) -> bool:
        return self.premium_days > 0


CATALOG: tuple[Product, ...] = (
    Product(
        code="lord_month",
        title="👑 Лорд на 30 дней",
        description="10 слов в день вместо 3, 30 боёв, повышенный шанс легендарных карт, "
        "комиссия 5%, золотая корона в топе и +100 💎 при каждом продлении. Отключить можно в любой момент.",
        stars=249,
        rub=399,
        premium_days=30,
        subscription=True,
        ref_value=250,
        badge="🔥",
    ),
    Product(
        code="lord_week",
        title="👑 Лорд на 7 дней",
        description="Неделя статуса Лорда: 10 слов в день, 30 боёв, повышенный шанс легендарных карт и +100 💎.",
        stars=79,
        rub=149,
        premium_days=7,
        ref_value=80,
    ),
    Product(
        code="cr100",
        title="100 кристаллов",
        description="100 💎 — на перья для новых слов, захваты, щиты и аукционы.",
        stars=50,
        rub=99,
        crystals=100,
        ref_value=100,
    ),
    Product(
        code="cr300",
        title="300 кристаллов",
        description="300 💎 (выгода 7%) — на перья, захваты, щиты и аукционы.",
        stars=139,
        rub=249,
        crystals=300,
        ref_value=300,
    ),
    Product(
        code="cr1000",
        title="1000 кристаллов",
        description="1000 💎 (выгода 20%) — хватит, чтобы выиграть аукцион легендарного слова.",
        stars=399,
        rub=690,
        crystals=1000,
        ref_value=1000,
        badge="⭐",
    ),
    Product(
        code="cr3000",
        title="3000 кристаллов",
        description="3000 💎 (выгода 34%) — для настоящих магнатов мира слов.",
        stars=990,
        rub=1790,
        crystals=3000,
        ref_value=3000,
    ),
)

PRODUCTS: dict[str, Product] = {p.code: p for p in CATALOG}


def get_product(code: str) -> Product | None:
    return PRODUCTS.get(code)


def make_payload(product: Product, user_id: int) -> str:
    return f"{product.code}:{user_id}"


def parse_payload(payload: str) -> tuple[str, int] | None:
    code, sep, user_id = payload.partition(":")
    if not sep or not user_id.isdigit():
        return None
    return code, int(user_id)
