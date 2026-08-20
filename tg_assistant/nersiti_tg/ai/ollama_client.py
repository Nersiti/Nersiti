"""Тонкий httpx-клиент к локальному Ollama (127.0.0.1:11434).

Контракт (async):
    async generate(prompt, system=None, **opts) -> str      # /api/generate
    async chat(messages: list[dict], **opts) -> str          # /api/chat
    async embed(text) -> list[float]                         # /api/embeddings
Понятная ошибка, если Ollama не запущен.
TODO(исполнитель): по docs/PLAN.md §7.
"""
# TODO
