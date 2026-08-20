"""Тонкий httpx-клиент к локальному Ollama (127.0.0.1:11434).

Контракт (async):
    async generate(prompt, system=None, **opts) -> str      # /api/generate
    async chat(messages, tools=None, **opts) -> dict          # /api/chat
        # при tools модель может вернуть tool_calls -> цикл в ai.reply (§7a)
    async embed(text) -> list[float]                         # /api/embeddings
Понятная ошибка, если Ollama не запущен.
TODO(исполнитель): по docs/PLAN.md §7. chat возвращает message целиком
(с content и возможным tool_calls), а не только строку.
"""
# TODO
