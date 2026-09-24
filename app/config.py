from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_SYSTEM_PROMPT = (
    "Ты — {bot_name}, умный и дружелюбный ИИ-ассистент в Telegram. "
    "Отвечай на языке пользователя (по умолчанию — на русском). "
    "Пиши ясно и по делу, структурируй ответ: короткие абзацы, списки, блоки кода. "
    "Используй Markdown (**жирный**, списки, ```код```). "
    "Не выдумывай факты: если не уверен — так и скажи."
)

DEFAULT_NEGATIVE = (
    "nsfw, nude, naked, lowres, bad anatomy, bad hands, extra fingers, missing fingers, "
    "deformed, blurry, jpeg artifacts, watermark, signature, text, logo, worst quality, low quality"
)


def _csv(value: Any) -> Any:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class Settings(BaseSettings):
    """All bot settings. Values come from environment variables or the .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Telegram ---
    bot_token: SecretStr
    admin_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)
    bot_name: str = "Nersiti AI"
    support_contact: str = ""  # @username для /paysupport
    database_url: str = "sqlite+aiosqlite:///data/bot.db"
    timezone: str = "Europe/Moscow"
    log_level: str = "INFO"
    throttle_seconds: float = 0.7

    # --- Текстовая нейросеть (любой OpenAI-совместимый API: Ollama, DeepSeek, OpenRouter, VseGPT...) ---
    llm_backend: Literal["openai", "mock"] = "openai"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: SecretStr = SecretStr("ollama")
    llm_model: str = "qwen2.5:7b"
    llm_system_prompt: str = DEFAULT_SYSTEM_PROMPT
    llm_temperature: float = 0.7
    llm_max_tokens: int = 1500
    llm_timeout: float = 180.0
    llm_concurrency: int = 4
    llm_stream: bool = True
    history_free: int = 6
    history_premium: int = 20

    # --- Генерация картинок ---
    image_backend: Literal["comfyui", "a1111", "openai", "mock"] = "comfyui"
    image_api_url: str = "http://localhost:8188"
    image_api_key: SecretStr = SecretStr("")
    image_model: str = "sd_xl_base_1.0.safetensors"
    comfy_workflow: str = "workflows/sdxl.json"
    image_steps: int = 28
    image_cfg: float = 6.0
    image_sampler: str = "DPM++ 2M Karras"
    image_size_scale: float = 1.0
    image_negative: str = DEFAULT_NEGATIVE
    image_translate: bool = True
    image_workers: int = 1
    image_timeout: float = 300.0

    # --- Экономика ---
    free_chat_per_day: int = 15
    free_images_per_day: int = 3
    premium_chat_per_day: int = 500
    premium_images_per_day: int = 60
    chat_cost: int = 1
    image_cost: int = 5
    start_bonus: int = 10
    ref_bonus_inviter: int = 15
    ref_bonus_invitee: int = 10
    ref_percent: int = 10
    daily_bonus: int = 3
    ad_every: int = 5

    # --- Оплата ---
    stars_enabled: bool = True
    rub_provider_token: SecretStr = SecretStr("")  # платёжный токен из @BotFather (ЮKassa, Robokassa и т.п.)
    rub_receipt: bool = False  # передавать данные чека (54-ФЗ) провайдеру
    rub_vat_code: int = 1
    yookassa_shop_id: str = ""
    yookassa_secret_key: SecretStr = SecretStr("")
    yookassa_return_url: str = ""
    yookassa_receipt_email: str = ""

    # --- Продвижение ---
    required_channels: Annotated[list[str], NoDecode] = Field(default_factory=list)
    showcase_channel: str = ""
    showcase_interval_minutes: int = 180
    showcase_prompts_file: str = "promo/showcase_prompts.txt"

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

    @property
    def system_prompt(self) -> str:
        return self.llm_system_prompt.replace("{bot_name}", self.bot_name)

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
