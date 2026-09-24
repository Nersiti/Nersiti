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
    stars: int  # цена в Telegram Stars
    rub: int  # цена в рублях (целые рубли)
    credits: int = 0
    premium_days: int = 0
    subscription: bool = False  # при оплате Stars — автопродление каждые 30 дней
    ref_value: int = 0  # база для реферальной комиссии (в кредитах)
    badge: str = ""

    @property
    def is_premium(self) -> bool:
        return self.premium_days > 0


CATALOG: tuple[Product, ...] = (
    Product(
        code="prem_month",
        title="Premium на 30 дней",
        description="Безлимитный ИИ-чат, до 60 картинок в день, приоритетная очередь, без рекламы. "
        "При оплате звёздами продлевается автоматически, отключить можно в любой момент.",
        stars=299,
        rub=499,
        premium_days=30,
        subscription=True,
        ref_value=250,
        badge="🔥",
    ),
    Product(
        code="prem_week",
        title="Premium на 7 дней",
        description="Попробуйте все возможности Premium на неделю: безлимитный чат, "
        "до 60 картинок в день, приоритет.",
        stars=99,
        rub=179,
        premium_days=7,
        ref_value=80,
    ),
    Product(
        code="c50",
        title="50 кредитов",
        description="50 кредитов: 50 сообщений ИИ или 10 картинок. Кредиты не сгорают.",
        stars=50,
        rub=99,
        credits=50,
        ref_value=50,
    ),
    Product(
        code="c150",
        title="150 кредитов",
        description="150 кредитов (выгода 14%): 150 сообщений ИИ или 30 картинок. Кредиты не сгорают.",
        stars=129,
        rub=249,
        credits=150,
        ref_value=150,
    ),
    Product(
        code="c500",
        title="500 кредитов",
        description="500 кредитов (выгода 24%): 500 сообщений ИИ или 100 картинок. Кредиты не сгорают.",
        stars=379,
        rub=690,
        credits=500,
        ref_value=500,
        badge="⭐",
    ),
    Product(
        code="c1500",
        title="1500 кредитов",
        description="1500 кредитов (выгода 34%): 1500 сообщений ИИ или 300 картинок. Кредиты не сгорают.",
        stars=990,
        rub=1790,
        credits=1500,
        ref_value=1500,
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
