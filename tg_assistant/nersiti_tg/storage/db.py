"""Схема SQLite (+FTS5), соединение, CRUD.

Контракт: init_db(path), get_conn(), upsert_chat(...), insert_message(...),
mark_deleted(chat_id, tg_message_id), get_chat_settings(chat_id),
set_chat_settings(...), CRUD drafts.
Для «Архива чата» (§10):
    get_chat_history(chat_id, limit, offset, q=None) -> list[Message]
        # все сообщения чата по дате: вх./исх., удалённые (is_deleted),
        # версии правок (по edited_at), с media_id; опц. фильтр q по тексту.
Таблицы: chats, messages, messages_fts, media, chat_settings, drafts (PLAN.md §5).
TODO(исполнитель): stdlib sqlite3, включить FTS5, миграции идемпотентны.
"""
# TODO
