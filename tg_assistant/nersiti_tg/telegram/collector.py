"""Сборщик архива из событий Telethon: сообщения, медиа, видео (с дедупом).

Логика извлечения полей вынесена в чистые функции (message_to_record, media_kind,
is_video) — они тестируются без Telegram на фейковых объектах. Асинхронные
обработчики вешаются на клиент в register().
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..storage.models import Chat, Media, Message


def _to_unix(date: Any) -> int:
    if isinstance(date, datetime):
        return int(date.timestamp())
    if isinstance(date, (int, float)):
        return int(date)
    return 0


def media_kind(msg: Any) -> Optional[str]:
    if getattr(msg, "photo", None):
        return "photo"
    if getattr(msg, "video", None) or getattr(msg, "video_note", None):
        return "video"
    if getattr(msg, "voice", None):
        return "voice"
    if getattr(msg, "document", None):
        return "document"
    if getattr(msg, "sticker", None):
        return "sticker"
    return None


def is_video(msg: Any) -> bool:
    if getattr(msg, "video", None) or getattr(msg, "video_note", None):
        return True
    doc = getattr(msg, "document", None)
    mime = getattr(doc, "mime_type", "") if doc else ""
    return bool(mime and str(mime).startswith("video/"))


def message_to_record(msg: Any, chat_id: int, sender_name: str = "",
                      is_secret: int = 0) -> dict[str, Any]:
    """Пляский словарь полей для storage.Message. Чистая функция (тестируемо)."""
    ttl = 1 if getattr(msg, "ttl_seconds", None) else 0
    return {
        "tg_message_id": int(getattr(msg, "id", 0) or 0),
        "chat_id": int(chat_id),
        "sender_id": int(getattr(msg, "sender_id", 0) or 0),
        "sender_name": sender_name,
        "text": getattr(msg, "message", None) or getattr(msg, "text", "") or "",
        "date": _to_unix(getattr(msg, "date", 0)),
        "reply_to": int(getattr(msg, "reply_to_msg_id", 0) or 0),
        "is_outgoing": 1 if getattr(msg, "out", False) else 0,
        "was_disappearing": ttl,
        "self_destruct": ttl,
        "is_secret": is_secret,
        "ttl": ttl,
    }


class Collector:
    def __init__(self, db, videos, settings):
        self.db = db
        self.videos = videos
        self.settings = settings

    def register(self, client) -> None:
        from telethon import events  # ленивый импорт
        client.add_event_handler(self._on_new, events.NewMessage())
        client.add_event_handler(self._on_edit, events.MessageEdited())
        client.add_event_handler(self._on_delete, events.MessageDeleted())
        self._client = client

    async def _chat_title(self, event) -> tuple[int, str, str]:
        chat = await event.get_chat()
        cid = int(getattr(event, "chat_id", 0) or 0)
        title = getattr(chat, "title", None) or getattr(chat, "first_name", "") or ""
        ctype = "channel" if getattr(chat, "broadcast", False) else (
            "group" if getattr(chat, "megagroup", False) else "user")
        self.db.upsert_chat(Chat(chat_id=cid, type=ctype, title=title,
                                 last_seen_at=0))
        return cid, title, ctype

    async def _on_new(self, event) -> None:
        msg = event.message
        cid, _title, _type = await self._chat_title(event)
        rec = message_to_record(msg, cid)
        media_id = None
        kind = media_kind(msg)
        if kind and self.settings.archive.save_media:
            media_id = await self._download(event, msg, cid, kind)
        row = Message(id=None, media_id=media_id, **rec)
        self.db.insert_message(row)

    async def _download(self, event, msg, chat_id: int, kind: str) -> Optional[int]:
        sub = self.settings.media_dir / str(chat_id) / datetime.now().strftime("%Y-%m")
        sub.mkdir(parents=True, exist_ok=True)
        try:
            path = await event.client.download_media(msg, file=str(sub) + "/")
        except Exception:
            return None
        if not path:
            return None
        size = Path(path).stat().st_size if Path(path).exists() else 0
        media_id = self.db.insert_media(Media(
            id=None, chat_id=chat_id, tg_message_id=int(getattr(msg, "id", 0) or 0),
            kind=kind, file_path=str(path), size=size))
        # видео -> прогон через дедуп/счётчик
        if kind == "video":
            try:
                self.videos.drop_video(path)
            except Exception:
                pass
        return media_id

    async def _on_edit(self, event) -> None:
        if not self.settings.archive.save_edits:
            return
        msg = event.message
        cid = int(getattr(event, "chat_id", 0) or 0)
        rec = message_to_record(msg, cid)
        rec["edited_at"] = _to_unix(getattr(msg, "edit_date", 0)) or 1
        self.db.insert_message(Message(id=None, media_id=None, **rec))

    async def _on_delete(self, event) -> None:
        if not self.settings.archive.save_deleted:
            return
        cid = int(getattr(event, "chat_id", 0) or 0)
        for mid in getattr(event, "deleted_ids", []) or []:
            self.db.mark_deleted(cid, int(mid))

    async def backfill(self, client, per_chat: int = 200) -> int:
        """Первичная выкачка последних сообщений по всем диалогам."""
        total = 0
        async for dialog in client.iter_dialogs():
            cid = int(dialog.id)
            self.db.upsert_chat(Chat(chat_id=cid, title=getattr(dialog, "name", "")))
            async for msg in client.iter_messages(dialog.id, limit=per_chat):
                rec = message_to_record(msg, cid)
                self.db.insert_message(Message(id=None, media_id=None, **rec))
                total += 1
        return total
