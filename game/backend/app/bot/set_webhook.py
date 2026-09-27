"""Run once per deploy: python -m app.bot.set_webhook"""

import asyncio

from aiogram.types import BotCommand

from app.bot.instance import get_bot, get_dispatcher
from app.config import get_settings

COMMANDS = {
    "ru": [
        BotCommand(command="start", description="Открыть игру"),
        BotCommand(command="newclan", description="Создать клан"),
        BotCommand(command="help", description="Помощь"),
        BotCommand(command="paysupport", description="Вопросы по оплате"),
    ],
    "en": [
        BotCommand(command="start", description="Open the game"),
        BotCommand(command="newclan", description="Create a clan"),
        BotCommand(command="help", description="Help"),
        BotCommand(command="paysupport", description="Payment support"),
    ],
}


async def main() -> None:
    settings = get_settings()
    bot = get_bot()
    await bot.set_webhook(
        url=settings.webhook_url,
        secret_token=settings.webhook_secret,
        allowed_updates=get_dispatcher().resolve_used_update_types(),
        drop_pending_updates=False,
    )
    await bot.set_my_commands(COMMANDS["en"])
    await bot.set_my_commands(COMMANDS["ru"], language_code="ru")
    info = await bot.get_webhook_info()
    print(f"Webhook set: {info.url} (pending updates: {info.pending_update_count})")
    await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
