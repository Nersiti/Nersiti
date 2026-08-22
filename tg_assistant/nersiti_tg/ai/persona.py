"""Редактируемая персона/память ассистента (persona.md)."""
from __future__ import annotations

from pathlib import Path

DEFAULT_PERSONA = """\
Ты — личный ассистент пользователя в Telegram. Отвечай кратко, по-русски,
в дружелюбном естественном тоне, как будто пишет сам пользователь.
Не выдумывай факты. Если нужна свежая информация — используй инструменты поиска.
"""


class Persona:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def get(self) -> str:
        if self.path.exists():
            return self.path.read_text(encoding="utf-8")
        return DEFAULT_PERSONA

    def update(self, text: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(text, encoding="utf-8")

    def append_memory(self, note: str) -> None:
        cur = self.get() if self.path.exists() else DEFAULT_PERSONA
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(cur.rstrip() + f"\n\n## Заметка\n{note}\n", encoding="utf-8")
