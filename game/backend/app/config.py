from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # "prod" | "dev" | "test"
    env: str = "prod"
    dev_mode: bool = False

    bot_token: str
    bot_username: str = "world_battle_bot"
    webhook_secret: str
    domain: str = "localhost"

    database_url: str = "postgresql+asyncpg://game:game@postgres:5432/game"
    redis_url: str = "redis://redis:6379/0"

    # Comma-separated Telegram user ids: "123,456"
    admin_ids: str = ""

    game_name: str = "Битва за Мир"
    init_data_ttl_seconds: int = 86400

    adsgram_block_id: str = ""
    ads_callback_secret: str = ""

    @property
    def webapp_url(self) -> str:
        return f"https://{self.domain}/"

    @property
    def webhook_url(self) -> str:
        return f"https://{self.domain}/tg/webhook"

    @property
    def admin_id_set(self) -> set[int]:
        return {int(x) for x in self.admin_ids.replace(" ", "").split(",") if x}

    def check_safety(self) -> None:
        if self.dev_mode and self.env == "prod":
            raise RuntimeError("DEV_MODE must never be enabled when ENV=prod")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.check_safety()
    return settings
