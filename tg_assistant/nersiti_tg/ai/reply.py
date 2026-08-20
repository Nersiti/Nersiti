"""Сборка контекста из истории и генерация ответа (только локальная модель).

Контракт (async):
    async make_reply(chat_id, incoming_text) -> str
Шаги: взять последние ai.context_messages из БД -> (опц.) RAG ->
system=персона+инструкция режима -> ollama_client.chat -> текст.
Только генерация, без отправки.
TODO(исполнитель): по docs/PLAN.md §7.
"""
# TODO
