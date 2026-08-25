"""ИИ-агент: Ollama с инструментами. По промту делает действия.

Инструменты:
  - search_archive(query)          — поиск по архиву переписки;
  - video_stats()                  — счётчики видео (скинуто/дубли);
  - dedup_folder(folder)           — удалить дубли видео в папке;
  - set_autoreply(chat, mode, ...) — настроить автоответ для чата;
  - send_video(chat, path)         — отправить видео в чат;
  - propose_channel_cleanup(criteria) — предложить каналы на выход (без удаления).

Действия с Telegram (send_video, propose_channel_cleanup) выполняются в loop
воркера через worker.submit (потокобезопасно). Разрушительный выход из каналов
агент НЕ делает сам — только предлагает; подтверждение — на вкладке «Чистка каналов».
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from .ai.ollama_client import OllamaClient
from .telegram.channels import ChannelManager


TOOLS = [
    {"type": "function", "function": {
        "name": "search_archive", "description": "Поиск по сохранённой переписке",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "video_stats", "description": "Счётчики видео: скинуто, дубли",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "dedup_folder", "description": "Удалить одинаковые видео в папке",
        "parameters": {"type": "object", "properties": {
            "folder": {"type": "string"}}, "required": ["folder"]}}},
    {"type": "function", "function": {
        "name": "set_autoreply",
        "description": "Настроить автоответ для чата (off/draft/auto; submode preset/generate/dialogue)",
        "parameters": {"type": "object", "properties": {
            "chat": {"type": "string"}, "mode": {"type": "string"},
            "submode": {"type": "string"}, "preset_text": {"type": "string"}},
            "required": ["chat", "mode"]}}},
    {"type": "function", "function": {
        "name": "send_message", "description": "Отправить текстовое сообщение в чат (по имени или id)",
        "parameters": {"type": "object", "properties": {
            "chat": {"type": "string"}, "text": {"type": "string"}},
            "required": ["chat", "text"]}}},
    {"type": "function", "function": {
        "name": "send_video", "description": "Отправить видео-файл в чат",
        "parameters": {"type": "object", "properties": {
            "chat": {"type": "string"}, "path": {"type": "string"}},
            "required": ["chat", "path"]}}},
    {"type": "function", "function": {
        "name": "propose_channel_cleanup",
        "description": "Предложить каналы на выход по критерию (без удаления)",
        "parameters": {"type": "object", "properties": {
            "criteria": {"type": "string"}}, "required": ["criteria"]}}},
]


class Agent:
    def __init__(self, settings, db, videos, ollama: OllamaClient, persona,
                 worker=None):
        self.settings = settings
        self.db = db
        self.videos = videos
        self.ollama = ollama
        self.persona = persona
        self.worker = worker

    # ---- вспомогательное ----
    def _resolve_chat_id(self, name: str) -> Optional[int]:
        name = (name or "").strip()
        # прямой id (в т.ч. из «id=NNN»)
        raw = name.lower().replace("id=", "").strip()
        if raw.lstrip("-").isdigit():
            return int(raw)
        low = name.lower()
        for c in self.db.list_chats():
            title = (c.get("title") or "").lower()
            if low and low in title:
                return int(c["chat_id"])
        return None

    async def _via_worker(self, coro) -> Any:
        if self.worker is None or self.worker.loop is None:
            raise RuntimeError("Telegram не подключён")
        return await asyncio.wrap_future(self.worker.submit(coro))

    # ---- исполнение инструментов ----
    async def _exec_tool(self, name: str, args: dict) -> str:
        try:
            if name == "search_archive":
                res = self.db.search_fts(args.get("query", ""), limit=10)
                if not res:
                    return "ничего не найдено"
                return "\n".join(f"[{r['sender_name']}] {r['text'][:100]}" for r in res)
            if name == "video_stats":
                return json.dumps(self.videos.stats(), ensure_ascii=False)
            if name == "dedup_folder":
                return json.dumps(self.videos.dedup_folder(args["folder"]),
                                  ensure_ascii=False)
            if name == "set_autoreply":
                cid = self._resolve_chat_id(args.get("chat", ""))
                if cid is None:
                    return f"чат '{args.get('chat')}' не найден"
                from .storage.models import ChatSettings
                self.db.set_chat_settings(ChatSettings(
                    chat_id=cid, mode=args.get("mode", "off"),
                    auto_submode=args.get("submode", "generate"),
                    preset_text=args.get("preset_text", ""), enabled=1))
                return f"автоответ для '{args.get('chat')}' -> {args.get('mode')}"
            if name == "send_message":
                cid = self._resolve_chat_id(args.get("chat", ""))
                if cid is None:
                    return f"чат '{args.get('chat')}' не найден"
                await self._via_worker(
                    self.worker.client.send_message(cid, args.get("text", "")))
                return f"сообщение отправлено в '{args.get('chat')}'"
            if name == "send_video":
                cid = self._resolve_chat_id(args.get("chat", ""))
                if cid is None:
                    return f"чат '{args.get('chat')}' не найден"
                await self._via_worker(
                    self.worker.client.send_file(cid, args["path"]))
                return f"видео отправлено в '{args.get('chat')}'"
            if name == "propose_channel_cleanup":
                mgr = ChannelManager(self.worker.client)
                res = await self._via_worker(
                    mgr.propose_cleanup(args.get("criteria", ""), self.ollama))
                titles = ", ".join(c["title"] for c in res.get("leave", [])) or "нет"
                return ("Предлагаю на выход: " + titles +
                        ". Подтверди на вкладке «Чистка каналов».")
            return f"неизвестный инструмент: {name}"
        except Exception as e:  # noqa
            return f"ошибка инструмента {name}: {e}"

    RU = " ВАЖНО: отвечай ВСЕГДА только на русском языке."

    async def chat_simple(self, user_text: str, history=None) -> str:
        """Быстрый ответ без инструментов (один прогон модели). history — прошлые реплики."""
        messages = [{"role": "system", "content": self.persona.get() + self.RU}]
        messages.extend(history or [])
        messages.append({"role": "user", "content": user_text})
        msg = await self.ollama.chat(messages)
        return (msg or {}).get("content", "") or ""

    # ---- основной цикл ----
    async def run(self, user_text: str, history=None, max_iters: int = 4) -> str:
        messages = [
            {"role": "system", "content": self.persona.get() + self.RU +
             "\nТы можешь вызывать инструменты для действий по просьбе пользователя."},
        ]
        messages.extend(history or [])
        messages.append({"role": "user", "content": user_text})
        for _ in range(max_iters):
            msg = await self.ollama.chat(messages, tools=TOOLS)
            calls = msg.get("tool_calls") or []
            if not calls:
                return msg.get("content", "") or "готово"
            messages.append(msg)
            for call in calls:
                fn = call.get("function", {})
                name = fn.get("name", "")
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                result = await self._exec_tool(name, args)
                messages.append({"role": "tool", "content": result})
        # финальный ответ без инструментов
        final = await self.ollama.chat(messages)
        return final.get("content", "") or "готово"
