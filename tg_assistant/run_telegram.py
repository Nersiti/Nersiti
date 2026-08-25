"""Безголовый коннектор Telegram: логин + архивация всего в папку.

Проверка подключения БЕЗ GUI. Запуск на ПК пользователя:
    # заранее в .env: TG_API_ID, TG_API_HASH
    python run_telegram.py                 # живая архивация (все чаты/каналы/медиа/видео)
    python run_telegram.py --backfill 300  # + подтянуть историю (по 300 сообщений на чат)
    python run_telegram.py --clean "выйти из крипто-каналов, что не открывал месяц"

Первый запуск запросит номер и код из Telegram (интерактивно), дальше — по сессии.
"""
from __future__ import annotations

import argparse
import asyncio

from nersiti_tg.ai.ollama_client import OllamaClient
from nersiti_tg.config import load_settings
from nersiti_tg.logging_setup import setup_logging
from nersiti_tg.media.video_manager import VideoManager
from nersiti_tg.storage.db import Database
from nersiti_tg.telegram.channels import ChannelManager
from nersiti_tg.telegram.client import build_client, start_client
from nersiti_tg.telegram.collector import Collector


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", type=int, default=0,
                    help="подтянуть историю: N сообщений на чат")
    ap.add_argument("--clean", type=str, default="",
                    help="чистка каналов по промту (спросит подтверждение)")
    args = ap.parse_args()

    settings = load_settings()
    settings.ensure_dirs()
    setup_logging("INFO", settings.log_path)

    db = Database(settings.db_path)
    videos = VideoManager(db, settings)
    ollama = OllamaClient(base_url=settings.ai.base_url, model=settings.ai.model)

    client = build_client(settings)
    await start_client(client)
    me = await client.get_me()
    print(f"Вошли как: {getattr(me, 'first_name', '')} "
          f"(@{getattr(me, 'username', '')}). Архив: {settings.data_path}")

    # режим чистки каналов
    if args.clean:
        mgr = ChannelManager(client)
        proposal = await mgr.propose_cleanup(args.clean, ollama)
        leave = proposal["leave"]
        if not leave:
            print("Под критерий ничего не подошло.")
            return
        print("Предлагаю выйти из каналов:")
        for c in leave:
            print(f"  - {c['title']} (id {c['id']})")
        ans = input(f"Выйти из {len(leave)} каналов? [y/N] ").strip().lower()
        if ans == "y":
            res = await mgr.leave_channels([c["id"] for c in leave])
            print(f"Вышли: {len(res['left'])}, ошибок: {len(res['failed'])}")
        else:
            print("Отменено. Ничего не удалено.")
        return

    # архивация
    collector = Collector(db, videos, settings)
    if args.backfill:
        print(f"Подтягиваю историю (по {args.backfill} на чат)…")
        n = await collector.backfill(client, per_chat=args.backfill)
        print(f"Готово, добавлено {n} сообщений. Статистика: {db.stats()}")

    collector.register(client)
    print("Живая архивация запущена. Пиши/получай сообщения — они пойдут в архив.")
    print("Ctrl+C для остановки.")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
