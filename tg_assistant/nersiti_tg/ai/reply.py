"""Генерация ответа: сборка контекста из истории + вызов Ollama.

Нейросеть подключается позже. Пока Ollama недоступен, generate_reply
возвращает (None, reason) — пайплайн не падает, а вызывающий код решает,
что делать (напр. в режиме preset ответ вообще не нужен).
"""
from __future__ import annotations

from typing import Optional

from .ollama_client import OllamaClient, OllamaUnavailable
from .persona import Persona


SUBMODE_INSTRUCTION = {
    "generate": "Сгенерируй один подходящий ответ на последнее сообщение.",
    "dialogue": ("Веди естественный диалог от лица пользователя, опираясь на всю "
                 "историю переписки. Ответь на последнее сообщение."),
}


async def generate_reply(
    ollama: OllamaClient,
    persona: Persona,
    history: list[dict],          # [{role, content}] по возрастанию времени
    incoming_text: str,
    submode: str = "generate",
) -> tuple[Optional[str], str]:
    """Возвращает (текст_ответа | None, причина/статус)."""
    system = persona.get() + "\n\n" + SUBMODE_INSTRUCTION.get(
        submode, SUBMODE_INSTRUCTION["generate"])
    messages = [{"role": "system", "content": system}]
    messages.extend(history)
    messages.append({"role": "user", "content": incoming_text})
    try:
        msg = await ollama.chat(messages)
        text = (msg or {}).get("content", "").strip()
        if not text:
            return None, "empty"
        return text, "ok"
    except OllamaUnavailable as e:
        return None, f"ollama_unavailable: {e}"
