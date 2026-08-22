"""Схема SQLite (+FTS5), соединение, CRUD. Ядро локального архива.

Класс Database инкапсулирует соединение и все операции. FTS5 включён для
полнотекстового поиска по сообщениям. Схема идемпотентна (CREATE IF NOT EXISTS).
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from .models import Chat, ChatSettings, Draft, Media, Message

SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    chat_id      INTEGER PRIMARY KEY,
    type         TEXT DEFAULT 'user',
    title        TEXT DEFAULT '',
    username     TEXT DEFAULT '',
    last_seen_at INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS media (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id       INTEGER,
    tg_message_id INTEGER,
    kind          TEXT,
    file_path     TEXT DEFAULT '',
    mime          TEXT DEFAULT '',
    size          INTEGER DEFAULT 0,
    downloaded    INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS messages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_message_id    INTEGER,
    chat_id          INTEGER,
    sender_id        INTEGER DEFAULT 0,
    sender_name      TEXT DEFAULT '',
    text             TEXT DEFAULT '',
    date             INTEGER DEFAULT 0,
    reply_to         INTEGER DEFAULT 0,
    is_outgoing      INTEGER DEFAULT 0,
    is_deleted       INTEGER DEFAULT 0,
    edited_at        INTEGER DEFAULT 0,
    media_id         INTEGER,
    was_disappearing INTEGER DEFAULT 0,
    self_destruct    INTEGER DEFAULT 0,
    is_secret        INTEGER DEFAULT 0,
    ttl              INTEGER DEFAULT 0,
    raw_json         TEXT DEFAULT '',
    UNIQUE(chat_id, tg_message_id, edited_at)
);
CREATE INDEX IF NOT EXISTS idx_msg_chat_date ON messages(chat_id, date);

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    text, sender_name, content='messages', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, text, sender_name)
    VALUES (new.id, new.text, new.sender_name);
END;
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, text, sender_name)
    VALUES ('delete', old.id, old.text, old.sender_name);
END;

CREATE TABLE IF NOT EXISTS chat_settings (
    chat_id      INTEGER PRIMARY KEY,
    mode         TEXT DEFAULT 'off',
    auto_submode TEXT DEFAULT 'generate',
    preset_text  TEXT DEFAULT '',
    enabled      INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS drafts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id    INTEGER,
    reply_to   INTEGER DEFAULT 0,
    text       TEXT DEFAULT '',
    status     TEXT DEFAULT 'pending',
    created_at INTEGER DEFAULT 0
);
"""


def _row_to_message(r: sqlite3.Row) -> Message:
    return Message(
        id=r["id"], tg_message_id=r["tg_message_id"], chat_id=r["chat_id"],
        sender_id=r["sender_id"], sender_name=r["sender_name"], text=r["text"],
        date=r["date"], reply_to=r["reply_to"], is_outgoing=r["is_outgoing"],
        is_deleted=r["is_deleted"], edited_at=r["edited_at"], media_id=r["media_id"],
        was_disappearing=r["was_disappearing"], self_destruct=r["self_destruct"],
        is_secret=r["is_secret"], ttl=r["ttl"], raw_json=r["raw_json"],
    )


class Database:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ---- chats ----
    def upsert_chat(self, chat: Chat) -> None:
        self.conn.execute(
            """INSERT INTO chats(chat_id, type, title, username, last_seen_at)
               VALUES(?,?,?,?,?)
               ON CONFLICT(chat_id) DO UPDATE SET
                 type=excluded.type, title=excluded.title,
                 username=excluded.username, last_seen_at=excluded.last_seen_at""",
            (chat.chat_id, chat.type, chat.title, chat.username,
             chat.last_seen_at or int(time.time())),
        )
        self.conn.commit()

    def list_chats(self) -> list[dict[str, Any]]:
        cur = self.conn.execute(
            "SELECT * FROM chats ORDER BY last_seen_at DESC")
        return [dict(r) for r in cur.fetchall()]

    # ---- media ----
    def insert_media(self, m: Media) -> int:
        cur = self.conn.execute(
            """INSERT INTO media(chat_id, tg_message_id, kind, file_path, mime, size, downloaded)
               VALUES(?,?,?,?,?,?,?)""",
            (m.chat_id, m.tg_message_id, m.kind, m.file_path, m.mime, m.size, m.downloaded),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    # ---- messages ----
    def insert_message(self, m: Message) -> int:
        cur = self.conn.execute(
            """INSERT OR IGNORE INTO messages(
                 tg_message_id, chat_id, sender_id, sender_name, text, date,
                 reply_to, is_outgoing, is_deleted, edited_at, media_id,
                 was_disappearing, self_destruct, is_secret, ttl, raw_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (m.tg_message_id, m.chat_id, m.sender_id, m.sender_name, m.text, m.date,
             m.reply_to, m.is_outgoing, m.is_deleted, m.edited_at, m.media_id,
             m.was_disappearing, m.self_destruct, m.is_secret, m.ttl, m.raw_json),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def mark_deleted(self, chat_id: int, tg_message_id: int) -> None:
        self.conn.execute(
            "UPDATE messages SET is_deleted=1 WHERE chat_id=? AND tg_message_id=?",
            (chat_id, tg_message_id),
        )
        self.conn.commit()

    def get_recent(self, chat_id: int, limit: int = 20) -> list[Message]:
        cur = self.conn.execute(
            """SELECT * FROM messages WHERE chat_id=?
               ORDER BY date DESC, id DESC LIMIT ?""",
            (chat_id, limit),
        )
        rows = [_row_to_message(r) for r in cur.fetchall()]
        rows.reverse()  # по возрастанию времени
        return rows

    def get_chat_history(self, chat_id: int, limit: int = 200,
                         offset: int = 0, q: Optional[str] = None) -> list[Message]:
        """Полный архив чата (для кнопки «Архив чата»)."""
        if q:
            cur = self.conn.execute(
                """SELECT * FROM messages WHERE chat_id=? AND text LIKE ?
                   ORDER BY date ASC, id ASC LIMIT ? OFFSET ?""",
                (chat_id, f"%{q}%", limit, offset),
            )
        else:
            cur = self.conn.execute(
                """SELECT * FROM messages WHERE chat_id=?
                   ORDER BY date ASC, id ASC LIMIT ? OFFSET ?""",
                (chat_id, limit, offset),
            )
        return [_row_to_message(r) for r in cur.fetchall()]

    def search_fts(self, query: str, limit: int = 50,
                   chat_id: Optional[int] = None) -> list[dict[str, Any]]:
        sql = (
            "SELECT m.* FROM messages_fts f JOIN messages m ON m.id=f.rowid "
            "WHERE messages_fts MATCH ?"
        )
        args: list[Any] = [query]
        if chat_id is not None:
            sql += " AND m.chat_id=?"
            args.append(chat_id)
        sql += " ORDER BY m.date DESC LIMIT ?"
        args.append(limit)
        cur = self.conn.execute(sql, args)
        return [dict(r) for r in cur.fetchall()]

    # ---- chat_settings ----
    def get_chat_settings(self, chat_id: int) -> Optional[ChatSettings]:
        cur = self.conn.execute(
            "SELECT * FROM chat_settings WHERE chat_id=?", (chat_id,))
        r = cur.fetchone()
        if not r:
            return None
        return ChatSettings(chat_id=r["chat_id"], mode=r["mode"],
                            auto_submode=r["auto_submode"],
                            preset_text=r["preset_text"], enabled=r["enabled"])

    def set_chat_settings(self, s: ChatSettings) -> None:
        self.conn.execute(
            """INSERT INTO chat_settings(chat_id, mode, auto_submode, preset_text, enabled)
               VALUES(?,?,?,?,?)
               ON CONFLICT(chat_id) DO UPDATE SET
                 mode=excluded.mode, auto_submode=excluded.auto_submode,
                 preset_text=excluded.preset_text, enabled=excluded.enabled""",
            (s.chat_id, s.mode, s.auto_submode, s.preset_text, s.enabled),
        )
        self.conn.commit()

    # ---- drafts ----
    def add_draft(self, d: Draft) -> int:
        cur = self.conn.execute(
            """INSERT INTO drafts(chat_id, reply_to, text, status, created_at)
               VALUES(?,?,?,?,?)""",
            (d.chat_id, d.reply_to, d.text, d.status, d.created_at or int(time.time())),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def list_pending(self) -> list[Draft]:
        cur = self.conn.execute(
            "SELECT * FROM drafts WHERE status='pending' ORDER BY created_at DESC")
        return [Draft(id=r["id"], chat_id=r["chat_id"], reply_to=r["reply_to"],
                      text=r["text"], status=r["status"], created_at=r["created_at"])
                for r in cur.fetchall()]

    def set_draft_status(self, draft_id: int, status: str,
                         text: Optional[str] = None) -> None:
        if text is None:
            self.conn.execute("UPDATE drafts SET status=? WHERE id=?", (status, draft_id))
        else:
            self.conn.execute("UPDATE drafts SET status=?, text=? WHERE id=?",
                              (status, text, draft_id))
        self.conn.commit()

    def get_draft(self, draft_id: int) -> Optional[Draft]:
        r = self.conn.execute("SELECT * FROM drafts WHERE id=?", (draft_id,)).fetchone()
        if not r:
            return None
        return Draft(id=r["id"], chat_id=r["chat_id"], reply_to=r["reply_to"],
                     text=r["text"], status=r["status"], created_at=r["created_at"])

    # ---- stats ----
    def stats(self) -> dict[str, int]:
        m = self.conn.execute("SELECT COUNT(*) c FROM messages").fetchone()["c"]
        f = self.conn.execute("SELECT COUNT(*) c FROM media").fetchone()["c"]
        c = self.conn.execute("SELECT COUNT(*) c FROM chats").fetchone()["c"]
        return {"messages": m, "files": f, "chats": c}
