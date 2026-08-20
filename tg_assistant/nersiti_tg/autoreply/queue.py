"""Очередь черновиков поверх storage.db.

Контракт:
    list_pending() -> list[Draft]
    async approve(client, draft_id, edited_text=None) -> None  # -> send_draft_now
    reject(draft_id) -> None
TODO(исполнитель): по docs/PLAN.md §8.
"""
# TODO
