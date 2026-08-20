"""Обработчики событий Telethon -> архив + автоответ.

Контракт (async):
    def register(client, deps) -> None   # вешает хэндлеры ниже
    async on_new_message(event)          # upsert_chat, media, insert, fts, autoreply
    async on_message_edited(event)       # версия правки (save_edits)
    async on_message_deleted(event)      # mark_deleted (save_deleted)
    async backfill(client, limit)        # первичная выкачка истории
TODO(исполнитель): по docs/PLAN.md §6. Входящие -> autoreply.engine.handle.
"""
# TODO
