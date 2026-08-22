"""Ядро автоответа (серверная логика для мод-клиента).

Мод-клиент присылает входящее сообщение и спрашивает, что делать. Движок по
настройкам чата решает:
  - OFF / enabled=0  -> action="none"
  - DRAFT            -> сохранить черновик, action="draft" (телефон покажет
                        его над полем ввода, отправка по кнопке пользователя)
  - AUTO             -> action="send" + текст (телефон отправляет сам):
        PRESET   -> заготовленный текст (работает без нейросети)
        GENERATE -> сгенерированный ответ
        DIALOGUE -> ответ с полным контекстом истории
Если модель недоступна и режим требует генерации — action="none" + причина.
"""
from __future__ import annotations

import time
from typing import Any

from ..ai.ollama_client import OllamaClient
from ..ai.persona import Persona
from ..ai.reply import generate_reply
from ..storage.db import Database
from ..storage.models import Draft
from .rules import Mode, AutoSubmode, effective_settings


def _history_for_llm(db: Database, chat_id: int, limit: int) -> list[dict[str, Any]]:
    msgs = db.get_recent(chat_id, limit=limit)
    out: list[dict[str, Any]] = []
    for m in msgs:
        role = "assistant" if m.is_outgoing else "user"
        if m.text:
            out.append({"role": role, "content": m.text})
    return out


async def decide(db: Database, ollama: OllamaClient, persona: Persona,
                 chat_id: int, incoming_text: str, defaults,
                 context_messages: int = 20) -> dict[str, Any]:
    s = effective_settings(db, chat_id, defaults)

    if s.mode == Mode.OFF.value or not s.enabled:
        return {"action": "none", "reason": "off"}

    # PRESET не требует нейросети
    if s.mode in (Mode.DRAFT.value, Mode.AUTO.value) and \
            s.auto_submode == AutoSubmode.PRESET.value:
        text = s.preset_text or defaults.default_preset_text
        if s.mode == Mode.AUTO.value:
            return {"action": "send", "text": text, "reason": "preset"}
        draft_id = db.add_draft(Draft(id=None, chat_id=chat_id, reply_to=0,
                                      text=text, status="pending",
                                      created_at=int(time.time())))
        return {"action": "draft", "draft_id": draft_id, "text": text,
                "reason": "preset"}

    # GENERATE / DIALOGUE — нужна модель
    history = _history_for_llm(db, chat_id, context_messages)
    text, status = await generate_reply(ollama, persona, history,
                                        incoming_text, submode=s.auto_submode)
    if text is None:
        return {"action": "none", "reason": status}

    if s.mode == Mode.AUTO.value:
        return {"action": "send", "text": text, "reason": status}
    draft_id = db.add_draft(Draft(id=None, chat_id=chat_id, reply_to=0,
                                  text=text, status="pending",
                                  created_at=int(time.time())))
    return {"action": "draft", "draft_id": draft_id, "text": text, "reason": status}
