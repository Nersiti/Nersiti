"""Схема SQLite (+FTS5), соединение, CRUD.

Контракт: init_db(path), get_conn(), upsert_chat(...), insert_message(...),
mark_deleted(chat_id, tg_message_id), get_chat_settings(chat_id),
set_chat_settings(...), CRUD drafts.
Таблицы: chats, messages, messages_fts, media, chat_settings, drafts (PLAN.md §5).
TODO(исполнитель): stdlib sqlite3, включить FTS5, миграции идемпотентны.
"""
# TODO
