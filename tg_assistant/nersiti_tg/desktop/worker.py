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
        self.me_id: int = 0

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
        try:
            me = await self.client.get_me()
            self.me_id = int(getattr(me, "id", 0) or 0)
        except Exception:
            self.me_id = 0
        self.collector = Collector(self.db, self.videos, self.settings,
                                   ollama=self.ollama, persona=self.persona)
        self.collector.register(self.client)

    async def list_dialogs(self, limit: int = 300) -> list:
        """Список диалогов как в Telegram: тип, непрочитанные, последнее сообщение."""
        out = []
        async for d in self.client.iter_dialogs(limit=limit):
            ent = d.entity
            if d.is_user:
                typ = "saved" if (getattr(ent, "is_self", False) or
                                  int(d.id) == self.me_id) else "user"
            elif d.is_channel and not d.is_group:
                typ = "channel"
            else:
                typ = "group"
            msg = d.message
            text = ""
            if msg is not None:
                text = getattr(msg, "message", "") or ""
                if not text and getattr(msg, "media", None):
                    text = "[медиа]"
            out.append({
                "id": int(d.id),
                "name": ("Избранное" if typ == "saved" else (d.name or str(d.id))),
                "type": typ,
                "unread": int(getattr(d, "unread_count", 0) or 0),
                "preview": text[:70],
                "date": int(d.date.timestamp()) if getattr(d, "date", None) else 0,
            })
        return out

    async def get_history(self, chat_id: int, limit: int = 50) -> list:
        out = []
        async for m in self.client.iter_messages(chat_id, limit=limit):
            text = getattr(m, "message", "") or ""
            if not text and getattr(m, "media", None):
                text = "[медиа]"
            out.append({"out": bool(getattr(m, "out", False)), "text": text,
                        "date": int(m.date.timestamp()) if getattr(m, "date", None) else 0})
        out.reverse()
        return out

    async def send_message(self, chat_id: int, text: str) -> bool:
        await self.client.send_message(chat_id, text)
        return True

    def submit(self, coro) -> Future:
        """Выполнить корутину в loop воркера. Вернуть concurrent.futures.Future."""
        if self.loop is None:
            f: Future = Future()
            f.set_exception(RuntimeError("Воркер не запущен"))
            return f
        return asyncio.run_coroutine_threadsafe(coro, self.loop)
