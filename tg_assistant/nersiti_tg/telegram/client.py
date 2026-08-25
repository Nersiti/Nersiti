"""Создание и авторизация Telethon-клиента (userbot, MTProto).

Даёт полный доступ к аккаунту: все чаты, каналы, история, медиа, видео.
Первый запуск — интерактивный вход (номер -> код из Telegram -> 2FA при наличии).
Сессия хранится в папке архива (data_dir/session).
"""
from __future__ import annotations


def build_client(settings):
    """Вернуть TelegramClient. Telethon импортируется лениво."""
    from telethon import TelegramClient  # ленивый импорт

    if not settings.secrets.tg_api_id or not settings.secrets.tg_api_hash:
        raise RuntimeError(
            "Нет TG_API_ID / TG_API_HASH. Получи их на https://my.telegram.org "
            "и задай в .env (см. .env.example).")

    settings.ensure_dirs()
    session_path = str(settings.data_path / "session")
    return TelegramClient(session_path, settings.secrets.tg_api_id,
                          settings.secrets.tg_api_hash)


async def start_client(client) -> None:
    """Запустить и авторизовать клиент (интерактивно при первом входе)."""
    await client.start()
