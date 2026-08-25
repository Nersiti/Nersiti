"""Бэкенд-мозг: FastAPI-приложение.

Содержит:
  - sync-API для мод-клиента (телефон): /sync/messages, /sync/media, /ai/reply, /health
  - API панели: чаты, архив чата, поиск, черновики, настройки чата, персона

Аутентификация sync-эндпоинтов — заголовок X-Sync-Token == settings.secrets.sync_token.
Слушать только в локальной сети / через VPN.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from ..ai.ollama_client import OllamaClient
from ..ai.persona import Persona
from ..autoreply import engine, queue
from ..media.video_manager import VideoManager
from ..storage.db import Database
from ..storage.models import Chat, ChatSettings, Media, Message


# ---------- схемы запросов ----------
class InMessage(BaseModel):
    tg_message_id: int
    chat_id: int
    chat_type: str = "user"
    chat_title: str = ""
    sender_id: int = 0
    sender_name: str = ""
    text: str = ""
    date: int = 0
    reply_to: int = 0
    is_outgoing: int = 0
    is_deleted: int = 0
    edited_at: int = 0
    was_disappearing: int = 0
    self_destruct: int = 0
    is_secret: int = 0
    ttl: int = 0
    raw_json: str = ""


class SyncMessages(BaseModel):
    messages: list[InMessage]


class ReplyRequest(BaseModel):
    chat_id: int
    incoming_text: str


class ChatSettingsIn(BaseModel):
    mode: str = "off"
    auto_submode: str = "generate"
    preset_text: str = ""
    enabled: int = 1


class VideoPath(BaseModel):
    path: str


class DedupFolder(BaseModel):
    folder: str
    delete: Optional[bool] = None


def create_app(settings, db: Database, ollama: OllamaClient,
               persona: Persona) -> FastAPI:
    app = FastAPI(title="Nersiti backend")
    videos = VideoManager(db, settings)

    def check_token(x_sync_token: str = Header(default="")) -> None:
        if x_sync_token != settings.secrets.sync_token:
            raise HTTPException(status_code=401, detail="bad sync token")

    # ---------------- служебное ----------------
    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "stats": db.stats(),
                "ollama": await ollama.available()}

    # ---------------- sync (телефон -> ПК) ----------------
    @app.post("/sync/messages")
    async def sync_messages(body: SyncMessages,
                            _: None = Depends(check_token)) -> dict[str, Any]:
        saved = 0
        for im in body.messages:
            db.upsert_chat(Chat(chat_id=im.chat_id, type=im.chat_type,
                                title=im.chat_title,
                                last_seen_at=im.date or int(time.time())))
            if im.is_deleted:
                db.mark_deleted(im.chat_id, im.tg_message_id)
            db.insert_message(Message(
                id=None, tg_message_id=im.tg_message_id, chat_id=im.chat_id,
                sender_id=im.sender_id, sender_name=im.sender_name, text=im.text,
                date=im.date or int(time.time()), reply_to=im.reply_to,
                is_outgoing=im.is_outgoing, is_deleted=im.is_deleted,
                edited_at=im.edited_at, was_disappearing=im.was_disappearing,
                self_destruct=im.self_destruct, is_secret=im.is_secret,
                ttl=im.ttl, raw_json=im.raw_json))
            saved += 1
        return {"saved": saved}

    @app.post("/sync/media")
    async def sync_media(chat_id: int = Form(...), tg_message_id: int = Form(...),
                         kind: str = Form("document"), mime: str = Form(""),
                         file: UploadFile = File(...),
                         _: None = Depends(check_token)) -> dict[str, Any]:
        sub = settings.media_dir / str(chat_id) / time.strftime("%Y-%m")
        sub.mkdir(parents=True, exist_ok=True)
        dest = sub / f"{tg_message_id}_{file.filename}"
        data = await file.read()
        dest.write_bytes(data)
        media_id = db.insert_media(Media(id=None, chat_id=chat_id,
                                         tg_message_id=tg_message_id, kind=kind,
                                         file_path=str(dest), mime=mime,
                                         size=len(data)))
        return {"media_id": media_id, "path": str(dest), "size": len(data)}

    @app.post("/ai/reply")
    async def ai_reply(body: ReplyRequest,
                       _: None = Depends(check_token)) -> dict[str, Any]:
        return await engine.decide(db, ollama, persona, body.chat_id,
                                   body.incoming_text, settings.autoreply,
                                   settings.ai.context_messages)

    # ---------------- API панели ----------------
    @app.get("/api/chats")
    async def api_chats() -> list[dict[str, Any]]:
        chats = db.list_chats()
        for c in chats:
            s = db.get_chat_settings(c["chat_id"])
            c["settings"] = (s.__dict__ if s else
                             {"mode": settings.autoreply.default_mode,
                              "auto_submode": settings.autoreply.default_auto_submode,
                              "preset_text": settings.autoreply.default_preset_text,
                              "enabled": 1})
        return chats

    @app.get("/api/chat/{chat_id}/archive")
    async def api_archive(chat_id: int, limit: int = 200, offset: int = 0,
                          q: Optional[str] = None) -> list[dict[str, Any]]:
        return [m.__dict__ for m in
                db.get_chat_history(chat_id, limit=limit, offset=offset, q=q)]

    @app.post("/api/chat/{chat_id}/settings")
    async def api_set_settings(chat_id: int, body: ChatSettingsIn) -> dict[str, Any]:
        db.set_chat_settings(ChatSettings(chat_id=chat_id, mode=body.mode,
                                          auto_submode=body.auto_submode,
                                          preset_text=body.preset_text,
                                          enabled=body.enabled))
        return {"ok": True}

    @app.get("/api/search")
    async def api_search(q: str, limit: int = 50) -> list[dict[str, Any]]:
        return db.search_fts(q, limit=limit)

    @app.get("/api/drafts")
    async def api_drafts() -> list[dict[str, Any]]:
        return [d.__dict__ for d in queue.list_pending(db)]

    @app.post("/api/drafts/{draft_id}/approve")
    async def api_approve(draft_id: int, text: Optional[str] = None) -> dict[str, Any]:
        d = queue.approve(db, draft_id, edited_text=text)
        if d is None:
            raise HTTPException(status_code=404, detail="draft not found")
        return d.__dict__

    @app.post("/api/drafts/{draft_id}/reject")
    async def api_reject(draft_id: int) -> dict[str, Any]:
        queue.reject(db, draft_id)
        return {"ok": True}

    # ---------------- видео: дедупликация и подсчёт ----------------
    @app.post("/video/drop")
    async def video_drop(body: VideoPath) -> dict[str, Any]:
        return videos.drop_video(body.path)

    @app.post("/video/dedup")
    async def video_dedup(body: DedupFolder) -> dict[str, Any]:
        return videos.dedup_folder(body.folder, delete=body.delete)

    @app.get("/video/stats")
    async def video_stats() -> dict[str, Any]:
        return videos.stats()

    @app.get("/api/persona")
    async def api_get_persona() -> dict[str, str]:
        return {"persona": persona.get()}

    @app.post("/api/persona")
    async def api_set_persona(text: str = Form(...)) -> dict[str, Any]:
        persona.update(text)
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        st = db.stats()
        return (
            "<!doctype html><meta charset='utf-8'>"
            "<title>Nersiti backend</title>"
            "<h1>Nersiti — бэкенд-мозг</h1>"
            f"<p>Сообщений: {st['messages']} · Файлов: {st['files']} · "
            f"Чатов: {st['chats']}</p>"
            "<p>API: /health, /sync/messages, /sync/media, /ai/reply, "
            "/api/chats, /api/chat/{id}/archive, /api/search, /api/drafts</p>"
        )

    return app
