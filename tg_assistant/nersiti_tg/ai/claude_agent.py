"""ИИ-ассистент на Claude (Anthropic API) — умный, по-русски, с инструментами.

Включается, если задан ключ ANTHROPIC_API_KEY. Инструменты те же, что у
локального агента — переиспользуем его _exec_tool, только цикл под формат
Anthropic (tool_use / tool_result).
"""
from __future__ import annotations

SYSTEM_RU = ("Ты — встроенный ассистент приложения Nersiti (поверх Telegram). "
             "Отвечай ВСЕГДА на русском, кратко и по делу. Когда пользователь "
             "просит действие (отправить сообщение/видео, включить автоответ, "
             "чистка каналов, поиск по архиву) — вызывай подходящий инструмент. "
             "Если в тексте есть 'id=NNN' — это id чата, используй его.")

# Инструменты в формате Anthropic (input_schema)
TOOLS = [
    {"name": "search_archive", "description": "Поиск по сохранённой переписке",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}},
                      "required": ["query"]}},
    {"name": "video_stats", "description": "Счётчики видео (скинуто, дубли)",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "dedup_folder", "description": "Удалить одинаковые видео в папке",
     "input_schema": {"type": "object", "properties": {"folder": {"type": "string"}},
                      "required": ["folder"]}},
    {"name": "set_autoreply",
     "description": "Настроить автоответ для чата (mode: off/draft/auto; submode: preset/generate/dialogue)",
     "input_schema": {"type": "object", "properties": {
         "chat": {"type": "string"}, "mode": {"type": "string"},
         "submode": {"type": "string"}, "preset_text": {"type": "string"}},
         "required": ["chat", "mode"]}},
    {"name": "send_message", "description": "Отправить текстовое сообщение в чат (имя или id)",
     "input_schema": {"type": "object", "properties": {
         "chat": {"type": "string"}, "text": {"type": "string"}},
         "required": ["chat", "text"]}},
    {"name": "send_video", "description": "Отправить видео-файл в чат",
     "input_schema": {"type": "object", "properties": {
         "chat": {"type": "string"}, "path": {"type": "string"}},
         "required": ["chat", "path"]}},
    {"name": "propose_channel_cleanup",
     "description": "Предложить каналы на выход по критерию (без удаления)",
     "input_schema": {"type": "object", "properties": {"criteria": {"type": "string"}},
                      "required": ["criteria"]}},
]


def _text_of(resp) -> str:
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()


class ClaudeAgent:
    def __init__(self, tool_agent, persona, api_key: str,
                 model: str = "claude-opus-5"):
        import anthropic  # ленивый импорт
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.tools_exec = tool_agent._exec_tool   # переиспользуем исполнение инструментов
        self.persona = persona
        self.model = model

    def _system(self) -> str:
        return self.persona.get() + "\n" + SYSTEM_RU

    async def chat_simple(self, user_text: str, history=None) -> str:
        """Простой ответ без инструментов (для обычного разговора)."""
        messages = (history or []) + [{"role": "user", "content": user_text}]
        resp = await self.client.messages.create(
            model=self.model, max_tokens=2000, system=self._system(), messages=messages)
        return _text_of(resp) or "…"

    async def run(self, user_text: str, history=None, max_iters: int = 5) -> str:
        """Ответ с инструментами (действия по промту)."""
        messages = list(history or []) + [{"role": "user", "content": user_text}]
        for _ in range(max_iters):
            resp = await self.client.messages.create(
                model=self.model, max_tokens=4000, system=self._system(),
                tools=TOOLS, messages=messages)
            if resp.stop_reason != "tool_use":
                return _text_of(resp) or "готово"
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for b in resp.content:
                if getattr(b, "type", "") == "tool_use":
                    out = await self.tools_exec(b.name, dict(b.input or {}))
                    results.append({"type": "tool_result", "tool_use_id": b.id,
                                    "content": str(out)})
            messages.append({"role": "user", "content": results})
        resp = await self.client.messages.create(
            model=self.model, max_tokens=2000, system=self._system(), messages=messages)
        return _text_of(resp) or "готово"
