"""dataclass-модели строк БД."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Chat:
    chat_id: int
    type: str = "user"          # user | group | channel | secret
    title: str = ""
    username: str = ""
    last_seen_at: int = 0


@dataclass
class Media:
    id: Optional[int]
    chat_id: int
    tg_message_id: int
    kind: str                   # photo | video | voice | document | sticker ...
    file_path: str = ""
    mime: str = ""
    size: int = 0
    downloaded: int = 1


@dataclass
class Message:
    id: Optional[int]
    tg_message_id: int
    chat_id: int
    sender_id: int = 0
    sender_name: str = ""
    text: str = ""
    date: int = 0
    reply_to: int = 0
    is_outgoing: int = 0
    is_deleted: int = 0
    edited_at: int = 0
    media_id: Optional[int] = None
    was_disappearing: int = 0
    self_destruct: int = 0
    is_secret: int = 0
    ttl: int = 0
    raw_json: str = ""


@dataclass
class ChatSettings:
    chat_id: int
    mode: str = "off"           # off | draft | auto
    auto_submode: str = "generate"  # preset | generate | dialogue
    preset_text: str = ""
    enabled: int = 1


@dataclass
class Draft:
    id: Optional[int]
    chat_id: int
    reply_to: int
    text: str
    status: str = "pending"     # pending | sent | rejected | edited
    created_at: int = 0
