"""Поиск по архиву.

Контракт:
    def search_fts(query, limit=50, chat_id=None) -> list[dict]
    def search_semantic(chat_id, query, k=5) -> list[str]   # опц., через ai.embeddings
TODO(исполнитель): FTS5 MATCH; семантика — только если semantic_search.enabled.
"""
# TODO
