"""Видео: поиск одинаковых (дедупликация), чистка дублей, «скидывание» с подсчётом.

Понимание содержимого НЕ требуется. Одинаковость определяется по хэшу файла
(sha256) — точные копии находятся надёжно и без GPU. Опция near_duplicates
зарезервирована под перцептивный хэш (позже).

Счётчики хранятся в БД (таблица counters):
  - dropped_videos      — сколько видео «скинуто» (сохранено в архив);
  - duplicate_skipped   — сколько раз при скидывании попался дубликат;
  - duplicates_removed  — сколько файлов-дублей удалено при чистке папки.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".gif", ".ts"}


def file_hash(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def is_video(path: str | Path) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTS


class VideoManager:
    def __init__(self, db, config):
        self.db = db
        self.cfg = config
        self.saved_dir = Path(config.data_path) / config.video.saved_folder
        self.saved_dir.mkdir(parents=True, exist_ok=True)

    def drop_video(self, path: str | Path) -> dict:
        """«Скинуть» видео в архив с дедупликацией. Возвращает статус + счётчики."""
        path = Path(path)
        vhash = file_hash(path)
        size = path.stat().st_size
        is_dup, kept = self.db.register_video(vhash, str(path), size)
        if is_dup:
            dropped = self.db.get_counter("dropped_videos")
            skipped = self.db.incr_counter("duplicate_skipped")
            return {"status": "duplicate", "hash": vhash, "kept_path": kept,
                    "dropped_total": dropped, "duplicate_skipped": skipped}
        dest = self.saved_dir / path.name
        if path.resolve() != dest.resolve():
            shutil.copy2(path, dest)
            self.db.conn.execute("UPDATE videos SET file_path=? WHERE hash=?",
                                 (str(dest), vhash))
            self.db.conn.commit()
        dropped = self.db.incr_counter("dropped_videos")
        return {"status": "saved", "hash": vhash, "dest_path": str(dest),
                "dropped_total": dropped}

    def dedup_folder(self, folder: str | Path, delete: bool | None = None) -> dict:
        """Найти одинаковые видео в папке и удалить дубли, оставив по одному."""
        if delete is None:
            delete = self.cfg.video.delete_duplicates
        folder = Path(folder)
        seen: dict[str, Path] = {}
        removed, freed = [], 0
        for p in sorted(folder.rglob("*")):
            if not p.is_file() or not is_video(p):
                continue
            hh = file_hash(p)
            if hh in seen:
                freed += p.stat().st_size
                removed.append(str(p))
                if delete:
                    p.unlink(missing_ok=True)
            else:
                seen[hh] = p
        if removed:
            self.db.incr_counter("duplicates_removed", by=len(removed))
        return {"unique": len(seen), "removed": removed,
                "removed_count": len(removed), "freed_bytes": freed,
                "deleted": bool(delete)}

    def stats(self) -> dict:
        s = self.db.video_index_stats()
        s["dropped_videos"] = self.db.get_counter("dropped_videos")
        s["duplicate_skipped"] = self.db.get_counter("duplicate_skipped")
        s["duplicates_removed"] = self.db.get_counter("duplicates_removed")
        return s
