"""Режимы и per-chat настройки автоответа.

Контракт:
    class Mode(Enum): OFF, DRAFT, AUTO
    class AutoSubmode(Enum): PRESET, GENERATE, DIALOGUE
    обёртки над storage.db.get_chat_settings/set_chat_settings + дефолты из config.
TODO(исполнитель): по docs/PLAN.md §8.
"""
# TODO
