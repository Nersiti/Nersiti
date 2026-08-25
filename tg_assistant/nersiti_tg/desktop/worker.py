"""Фоновый Telegram-воркер для GUI.

Держит собственный asyncio-loop в отдельном потоке, подключает Telethon по
УЖЕ созданной сессии (вход сделан через run_telegram.py / nersiti_start.bat),
запускает живую архивацию и даёт GUI выполнять корутины потокобезопасно.
"""
from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future
from typing import Optional

from ..telegram.client import build_client
from ..telegram.collector import Collector


class TgWorker:
    def __init__(self, settings, db, videos, ollama=None, persona=None):
        self.settings = settings
        self.db = db
        self.videos = videos
        self.ollama = ollama
        self.persona = persona
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.client = None
        self.collector: Optional[Collector] = None
        self.thread: Optional[threading.Thread] = None
        self.ready = threading.Event()
        self.error: Optional[str] = None

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._setup())
        except Exception as e:  # noqa
            self.error = str(e)
            self.ready.set()
            return
        self.ready.set()
        self.loop.run_forever()

    async def _setup(self) -> None:
        self.client = build_client(self.settings)
        await self.client.connect()
        if not await self.client.is_user_authorized():
            raise RuntimeError(
                "Аккаунт не авторизован. Сначала войди через run_telegram.py "
                "или nersiti_start.bat, затем открой приложение.")
        self.collector = Collector(self.db, self.videos, self.settings,
                                   ollama=self.ollama, persona=self.persona)
        self.collector.register(self.client)

    def submit(self, coro) -> Future:
        """Выполнить корутину в loop воркера. Вернуть concurrent.futures.Future."""
        if self.loop is None:
            f: Future = Future()
            f.set_exception(RuntimeError("Воркер не запущен"))
            return f
        return asyncio.run_coroutine_threadsafe(coro, self.loop)
