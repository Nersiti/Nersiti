from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_NEGATIVE = (
    "text, letters, words, watermark, signature, logo, frame, border, nsfw, nude, lowres, blurry, "
    "bad anatomy, deformed, extra limbs, worst quality, low quality, jpeg artifacts"
)


def _csv(value: Any) -> Any:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class Settings(BaseSettings):
    """All settings come from environment variables or the .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Telegram ---
    bot_token: SecretStr
    admin_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)
    bot_name: str = "Хозяин Слова"
    support_contact: str = ""
    database_url: str = "sqlite+aiosqlite:///data/bot.db"
    timezone: str = "Europe/Moscow"
    log_level: str = "INFO"
    throttle_seconds: float = 0.5

    # --- Текстовая нейросеть (любой OpenAI-совместимый API) ---
    llm_backend: Literal["openai", "mock"] = "openai"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: SecretStr = SecretStr("ollama")
    llm_model: str = "qwen2.5:7b"
    llm_timeout: float = 90.0
    llm_concurrency: int = 4

    # --- Картинки для карт ---
    image_backend: Literal["comfyui", "a1111", "openai", "mock"] = "comfyui"
    image_api_url: str = "http://localhost:8188"
    image_api_key: SecretStr = SecretStr("")
    image_model: str = "sd_xl_base_1.0.safetensors"
    comfy_workflow: str = "workflows/sdxl.json"
    image_steps: int = 26
    image_cfg: float = 6.0
    image_sampler: str = "DPM++ 2M Karras"
    image_size_scale: float = 1.0
    image_negative: str = DEFAULT_NEGATIVE
    image_workers: int = 1
    image_timeout: float = 300.0

    # --- Экономика игры (в кристаллах 💎) ---
    start_crystals: int = 30
    free_quills_per_day: int = 3  # сколько слов в день можно захватить бесплатно
    lord_quills_per_day: int = 10
    quill_price: int = 15  # перо сверх лимита
    free_battles_per_day: int = 5
    lord_battles_per_day: int = 30
    battle_price: int = 3
    daily_bonus: int = 5
    immunity_hours: int = 48  # защита слова после захвата
    shield_days: int = 3
    shield_percent: int = 25  # цена щита — % от ценности слова
    fee_percent: int = 10  # комиссия игры с продаж и захватов (сжигается)
    lord_fee_percent: int = 5
    offer_ttl_hours: int = 24
    lord_bonus_crystals: int = 100  # бонус при каждой оплате «Лорда»
    ref_bonus_inviter: int = 30
    ref_bonus_invitee: int = 15
    ref_percent: int = 10
    ad_every: int = 4  # реклама бесплатным игрокам каждые N боёв (0 — выключить)

    # --- Аукцион «горячих» слов ---
    auction_enabled: bool = True
    auction_start_hour: int = 12
    auction_end_hour: int = 21
    auction_min_bid: int = 50
    auction_step_percent: int = 10
    auction_snipe_minutes: int = 5

    # --- Оплата ---
    stars_enabled: bool = True
    rub_provider_token: SecretStr = SecretStr("")
    rub_receipt: bool = False
    rub_vat_code: int = 1
    yookassa_shop_id: str = ""
    yookassa_secret_key: SecretStr = SecretStr("")
    yookassa_return_url: str = ""
    yookassa_receipt_email: str = ""

    # --- Продвижение ---
    required_channels: Annotated[list[str], NoDecode] = Field(default_factory=list)
    news_channel: str = ""  # канал «Хроника мира слов»: легендарные карты, захваты, аукционы

    @field_validator("admin_ids", "required_channels", mode="before")
    @classmethod
    def _split_csv(cls, value: Any) -> Any:
        return _csv(value)

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def rub_via_telegram(self) -> bool:
        return bool(self.rub_provider_token.get_secret_value())

    @property
    def yookassa_enabled(self) -> bool:
        return bool(self.yookassa_shop_id and self.yookassa_secret_key.get_secret_value())

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
