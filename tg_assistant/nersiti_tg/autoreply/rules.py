"""Режимы автоответа и доступ к per-chat настройкам."""
from __future__ import annotations

from enum import Enum

from ..storage.db import Database
from ..storage.models import ChatSettings


class Mode(str, Enum):
    OFF = "off"
    DRAFT = "draft"
    AUTO = "auto"


class AutoSubmode(str, Enum):
    PRESET = "preset"
    GENERATE = "generate"
    DIALOGUE = "dialogue"


def effective_settings(db: Database, chat_id: int, defaults) -> ChatSettings:
    """Настройки чата из БД или дефолты из config.autoreply."""
    s = db.get_chat_settings(chat_id)
    if s is not None:
        return s
    return ChatSettings(
        chat_id=chat_id,
        mode=defaults.default_mode,
        auto_submode=defaults.default_auto_submode,
        preset_text=defaults.default_preset_text,
        enabled=1,
    )
