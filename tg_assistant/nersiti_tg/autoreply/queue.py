"""Очередь черновиков поверх storage.db."""
from __future__ import annotations

from ..storage.db import Database
from ..storage.models import Draft


def list_pending(db: Database) -> list[Draft]:
    return db.list_pending()


def approve(db: Database, draft_id: int, edited_text: str | None = None) -> Draft | None:
    d = db.get_draft(draft_id)
    if d is None:
        return None
    status = "edited" if edited_text is not None else "sent"
    db.set_draft_status(draft_id, status, text=edited_text)
    return db.get_draft(draft_id)


def reject(db: Database, draft_id: int) -> None:
    db.set_draft_status(draft_id, "rejected")
