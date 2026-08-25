"""Тесты бэкенда: хранилище, архив (в т.ч. исчезающие/секретные), sync-API,
автоответ. Нейросеть НЕ требуется — режим preset и деградация без Ollama.

Запуск:  pytest -q
"""
from __future__ import annotations

import os
import tempfile

from fastapi.testclient import TestClient

from nersiti_tg.ai.ollama_client import OllamaClient
from nersiti_tg.ai.persona import Persona
from nersiti_tg.config import load_settings
from nersiti_tg.dashboard.app import create_app
from nersiti_tg.storage.db import Database
from nersiti_tg.storage.models import Chat, ChatSettings, Message


def _make():
    tmp = tempfile.mkdtemp()
    os.environ["NERSITI_DATA_DIR"] = tmp
    os.environ["SYNC_TOKEN"] = "secret"
    settings = load_settings(env_path="__none__", yaml_path="__none__")
    settings.ensure_dirs()
    db = Database(settings.db_path)
    ollama = OllamaClient(base_url="http://127.0.0.1:59999")  # заведомо недоступен
    persona = Persona(settings.persona_path)
    app = create_app(settings, db, ollama, persona)
    return settings, db, TestClient(app)


def test_storage_and_disappearing():
    _, db, _c = _make()
    db.upsert_chat(Chat(chat_id=1, title="Марина"))
    db.insert_message(Message(id=None, tg_message_id=10, chat_id=1,
                              sender_name="Марина", text="привет", date=100))
    # исчезающее + секретное
    db.insert_message(Message(id=None, tg_message_id=11, chat_id=1,
                              sender_name="Марина", text="секрет", date=101,
                              was_disappearing=1, self_destruct=1, is_secret=1))
    hist = db.get_chat_history(1)
    assert len(hist) == 2
    assert hist[1].self_destruct == 1 and hist[1].is_secret == 1
    # удаление сохраняет строку
    db.mark_deleted(1, 10)
    assert db.get_chat_history(1)[0].is_deleted == 1
    # поиск FTS
    assert db.search_fts("секрет")


def test_health_and_auth():
    _, _db, c = _make()
    assert c.get("/health").json()["ok"] is True
    # без токена — 401
    assert c.post("/sync/messages", json={"messages": []}).status_code == 401


def test_sync_and_archive_api():
    _, _db, c = _make()
    h = {"X-Sync-Token": "secret"}
    payload = {"messages": [{
        "tg_message_id": 5, "chat_id": 7, "chat_title": "Дима",
        "sender_name": "Дима", "text": "скинь фото", "date": 200,
        "was_disappearing": 1,
    }]}
    r = c.post("/sync/messages", json=payload, headers=h)
    assert r.json()["saved"] == 1
    arch = c.get("/api/chat/7/archive").json()
    assert arch[0]["text"] == "скинь фото" and arch[0]["was_disappearing"] == 1


def test_autoreply_preset_and_draft():
    settings, db, c = _make()
    # PRESET + AUTO -> сразу текст (без нейросети)
    db.set_chat_settings(ChatSettings(chat_id=2, mode="auto",
                                      auto_submode="preset",
                                      preset_text="я занят", enabled=1))
    r = c.post("/ai/reply", json={"chat_id": 2, "incoming_text": "ты тут?"},
               headers={"X-Sync-Token": "secret"}).json()
    assert r["action"] == "send" and r["text"] == "я занят"

    # GENERATE без Ollama -> action none (модель подключим позже)
    db.set_chat_settings(ChatSettings(chat_id=3, mode="auto",
                                      auto_submode="generate", enabled=1))
    r2 = c.post("/ai/reply", json={"chat_id": 3, "incoming_text": "как дела?"},
                headers={"X-Sync-Token": "secret"}).json()
    assert r2["action"] == "none"

    # DRAFT + PRESET -> черновик в очереди
    db.set_chat_settings(ChatSettings(chat_id=4, mode="draft",
                                      auto_submode="preset",
                                      preset_text="ок", enabled=1))
    c.post("/ai/reply", json={"chat_id": 4, "incoming_text": "привет"},
           headers={"X-Sync-Token": "secret"})
    drafts = c.get("/api/drafts").json()
    assert any(d["text"] == "ок" for d in drafts)


def test_password():
    from nersiti_tg.auth import check_password, hash_password
    h = hash_password("Logingood123337")
    assert check_password("Logingood123337", h)
    assert not check_password("wrong", h)


def test_video_dedup_and_count(tmp_path):
    from nersiti_tg.media.video_manager import VideoManager
    settings, db, _c = _make()
    vm = VideoManager(db, settings)

    # три файла: два одинаковых (дубли), один другой
    a = tmp_path / "a.mp4"; a.write_bytes(b"SAMEVIDEO")
    b = tmp_path / "b.mp4"; b.write_bytes(b"SAMEVIDEO")
    d = tmp_path / "d.mp4"; d.write_bytes(b"OTHER")

    r1 = vm.drop_video(a); assert r1["status"] == "saved"
    r2 = vm.drop_video(b); assert r2["status"] == "duplicate"  # тот же контент
    r3 = vm.drop_video(d); assert r3["status"] == "saved"
    assert vm.stats()["dropped_videos"] == 2      # скинуто уникальных
    assert vm.stats()["duplicate_skipped"] == 1

    # чистка папки с дублями
    folder = tmp_path / "dump"; folder.mkdir()
    (folder / "x.mp4").write_bytes(b"DUP")
    (folder / "y.mp4").write_bytes(b"DUP")
    (folder / "z.mp4").write_bytes(b"UNIQ")
    rep = vm.dedup_folder(folder, delete=True)
    assert rep["removed_count"] == 1 and rep["unique"] == 2
    assert not (folder / "y.mp4").exists() or not (folder / "x.mp4").exists()


def test_video_endpoints(tmp_path):
    _, _db, c = _make()
    v = tmp_path / "clip.mp4"; v.write_bytes(b"HELLOVIDEO")
    r = c.post("/video/drop", json={"path": str(v)}).json()
    assert r["status"] == "saved"
    assert c.get("/video/stats").json()["dropped_videos"] == 1


def test_collector_extract():
    from datetime import datetime
    from types import SimpleNamespace
    from nersiti_tg.telegram.collector import (message_to_record, media_kind,
                                               is_video)
    # обычное текстовое исходящее сообщение
    msg = SimpleNamespace(id=42, message="привет", date=datetime(2025, 1, 1),
                          out=True, sender_id=7, reply_to_msg_id=0,
                          ttl_seconds=None)
    rec = message_to_record(msg, chat_id=100)
    assert rec["tg_message_id"] == 42 and rec["is_outgoing"] == 1
    assert rec["chat_id"] == 100 and rec["date"] > 0
    # исчезающее видео
    vid = SimpleNamespace(id=43, message="", date=1700000000, out=False,
                          sender_id=8, reply_to_msg_id=0, ttl_seconds=5,
                          video=object())
    assert is_video(vid) and media_kind(vid) == "video"
    rv = message_to_record(vid, chat_id=100)
    assert rv["was_disappearing"] == 1 and rv["self_destruct"] == 1


def test_channel_cleanup_parse():
    from nersiti_tg.telegram.channels import parse_cleanup_decision
    channels = [{"id": 10, "title": "Крипта"}, {"id": 20, "title": "Новости"},
                {"id": 30, "title": "Мемы"}]
    assert parse_cleanup_decision('{"leave":[10,30]}', channels) == [10, 30]
    # fallback по числам
    assert parse_cleanup_decision("оставить только новости, выйти из 10 и 30",
                                  channels) == [10, 30]
