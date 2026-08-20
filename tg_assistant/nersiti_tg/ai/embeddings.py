"""Опциональная семантическая память (RAG). Включается semantic_search.enabled.

Контракт:
    def index_message(msg) -> None
    def search_semantic(chat_id, query, k) -> list[str]
Если выключено — no-op.
TODO(исполнитель): по docs/PLAN.md §7.
"""
# TODO
