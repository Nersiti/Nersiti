"""Nersiti Desktop — Windows-приложение (строгий чёрный стиль).

- пароль при каждом входе (SHA-256 из config.security, по умолчанию Logingood123337);
- подхватывает уже созданную сессию Telegram (вход через run_telegram.py) и
  ведёт живую архивацию + показывает реальные чаты/каналы;
- встроенный ИИ-чат (Ollama) под кнопкой «Ассистент»;
- чистка каналов по промту (двухшагово: предложить -> подтвердить);
- видео: дедупликация и счётчики.

Запуск:  python -m nersiti_tg.desktop.main   (из папки tg_assistant)
Требуется: pip install PySide6 telethon httpx
ВАЖНО: закрой окно run_telegram.py перед запуском приложения (одна сессия).
"""
from __future__ import annotations

import asyncio
import sys
import threading

from PySide6.QtCore import Qt, QTimer, QObject, Signal
from PySide6.QtWidgets import (
    QApplication, QDialog, QLineEdit, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QMainWindow, QWidget, QTabWidget, QListWidget, QListWidgetItem,
    QTextEdit, QFileDialog, QDockWidget, QMessageBox, QCheckBox, QScrollArea,
)

from ..auth import check_password
from ..ai.ollama_client import OllamaClient
from ..ai.persona import Persona
from ..config import load_settings
from ..media.video_manager import VideoManager
from ..storage.db import Database
from ..telegram.channels import ChannelManager
from .worker import TgWorker


DARK_QSS = """
* { color:#e8e8ea; font-family:'Segoe UI',sans-serif; font-size:13px; }
QWidget { background:#0a0a0b; }
QMainWindow, QDialog { background:#060607; }
QLineEdit, QTextEdit, QListWidget, QScrollArea {
  background:#111113; border:1px solid #242428; border-radius:8px; padding:8px; }
QLineEdit:focus, QTextEdit:focus { border:1px solid #3a3a42; }
QPushButton { background:#161619; border:1px solid #2a2a30; border-radius:8px; padding:8px 14px; }
QPushButton:hover { background:#1f1f24; }
QPushButton#primary { background:#1c1c22; border:1px solid #3a3a44; font-weight:600; }
QPushButton#danger { background:#241716; border:1px solid #4a2a25; color:#e0776b; }
QTabWidget::pane { border:1px solid #1c1c20; }
QTabBar::tab { background:#0d0d0e; padding:8px 16px; border:1px solid #1c1c20; border-bottom:none; }
QTabBar::tab:selected { background:#161619; }
QLabel#title { font-size:20px; font-weight:700; }
QLabel#muted { color:#7a7a82; }
QCheckBox { spacing:8px; }
QDockWidget::title { background:#0d0d0e; padding:6px; }
"""


class PasswordDialog(QDialog):
    def __init__(self, expected_hash: str):
        super().__init__()
        self.expected_hash = expected_hash
        self.ok = False
        self.setWindowTitle("Nersiti — вход")
        self.setFixedWidth(360)
        lay = QVBoxLayout(self)
        t = QLabel("Nersiti"); t.setObjectName("title")
        s = QLabel("Введите пароль"); s.setObjectName("muted")
        self.inp = QLineEdit(); self.inp.setEchoMode(QLineEdit.Password)
        self.inp.setPlaceholderText("Пароль"); self.inp.returnPressed.connect(self._try)
        b = QPushButton("Войти"); b.setObjectName("primary"); b.clicked.connect(self._try)
        self.err = QLabel(""); self.err.setStyleSheet("color:#e0554a")
        for w in (t, s, self.inp, self.err, b):
            lay.addWidget(w)

    def _try(self):
        if check_password(self.inp.text(), self.expected_hash):
            self.ok = True; self.accept()
        else:
            self.err.setText("Неверный пароль"); self.inp.clear()


class Bus(QObject):
    text = Signal(str)
    channels = Signal(list)


class AiChat(QDockWidget):
    def __init__(self, agent):
        super().__init__("ИИ-ассистент")
        self.agent = agent
        self.bus = Bus(); self.bus.text.connect(self._show)
        body = QWidget(); lay = QVBoxLayout(body)
        self.log = QTextEdit(); self.log.setReadOnly(True)
        row = QHBoxLayout()
        self.inp = QLineEdit()
        self.inp.setPlaceholderText("Напиши, что сделать… (отправь видео, включи автоответ, найди…)")
        self.inp.returnPressed.connect(self._send)
        snd = QPushButton("→"); snd.clicked.connect(self._send)
        row.addWidget(self.inp); row.addWidget(snd)
        lay.addWidget(self.log); lay.addLayout(row)
        self.setWidget(body)

    def _send(self):
        q = self.inp.text().strip()
        if not q:
            return
        self.log.append(f"<b>Вы:</b> {q}"); self.inp.clear()
        threading.Thread(target=self._ask, args=(q,), daemon=True).start()

    def _ask(self, q: str):
        try:
            answer = asyncio.run(self.agent.run(q))
            self.bus.text.emit(answer or "готово")
        except Exception as e:  # noqa
            self.bus.text.emit(f"[ИИ недоступен: {e}. Запущен ли Ollama?]")

    def _show(self, text: str):
        self.log.append(f"<b>Ассистент:</b> {text}")


class VideoTab(QWidget):
    def __init__(self, videos: VideoManager):
        super().__init__()
        self.videos = videos
        lay = QVBoxLayout(self)
        self.stats = QLabel(); self.stats.setObjectName("muted")
        drop = QPushButton("Скинуть видео (файлы)"); drop.setObjectName("primary"); drop.clicked.connect(self._drop)
        dedup = QPushButton("Найти и удалить дубли в папке…"); dedup.clicked.connect(self._dedup)
        for w in (QLabel("Видео: дедупликация и подсчёт"), drop, dedup, self.stats):
            lay.addWidget(w)
        lay.addStretch(1); self._refresh()

    def _refresh(self):
        s = self.videos.stats()
        self.stats.setText(
            f"Скинуто: {s['dropped_videos']} · Уникальных: {s['unique']} · "
            f"Пропущено дублей: {s['duplicate_skipped']} · Удалено дублей: {s['duplicates_removed']}")

    def _drop(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Выбрать видео")
        for f in files:
            try:
                self.videos.drop_video(f)
            except Exception:
                pass
        self._refresh()

    def _dedup(self):
        folder = QFileDialog.getExistingDirectory(self, "Папка с видео")
        if folder:
            rep = self.videos.dedup_folder(folder)
            QMessageBox.information(self, "Дедупликация",
                f"Удалено дублей: {rep['removed_count']}, освобождено: {rep['freed_bytes']} байт")
            self._refresh()


class ChannelsTab(QWidget):
    def __init__(self, worker: TgWorker, ollama: OllamaClient):
        super().__init__()
        self.worker, self.ollama = worker, ollama
        self.bus = Bus(); self.bus.channels.connect(self._show_proposal)
        self.proposal = []
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Чистка каналов по промту"))
        row = QHBoxLayout()
        self.prompt = QLineEdit()
        self.prompt.setPlaceholderText("напр.: выйти из крипто-каналов, что не открывал месяц")
        b = QPushButton("Предложить"); b.setObjectName("primary"); b.clicked.connect(self._propose)
        row.addWidget(self.prompt); row.addWidget(b)
        lay.addLayout(row)
        self.area = QVBoxLayout()
        holder = QWidget(); holder.setLayout(self.area)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(holder)
        lay.addWidget(scroll, 1)
        self.confirm = QPushButton("Подтвердить выход"); self.confirm.setObjectName("danger")
        self.confirm.clicked.connect(self._leave); self.confirm.setEnabled(False)
        self.info = QLabel(""); self.info.setObjectName("muted")
        lay.addWidget(self.confirm); lay.addWidget(self.info)
        self.checks = []

    def _propose(self):
        self.info.setText("Думаю…")
        prompt = self.prompt.text().strip()
        threading.Thread(target=self._propose_bg, args=(prompt,), daemon=True).start()

    def _propose_bg(self, prompt: str):
        try:
            mgr = ChannelManager(self.worker.client)
            fut = self.worker.submit(mgr.propose_cleanup(prompt, self.ollama))
            res = fut.result(timeout=120)
            self.bus.channels.emit(res.get("leave", []))
        except Exception as e:
            self.bus.channels.emit([{"error": str(e)}])

    def _show_proposal(self, leave):
        # очистить старое
        for c in self.checks:
            c.setParent(None)
        self.checks = []
        if leave and isinstance(leave[0], dict) and leave[0].get("error"):
            self.info.setText(f"Ошибка: {leave[0]['error']}"); self.confirm.setEnabled(False); return
        if not leave:
            self.info.setText("Под критерий ничего не подошло."); self.confirm.setEnabled(False); return
        self.proposal = leave
        for ch in leave:
            cb = QCheckBox(f"{ch['title']}  (id {ch['id']})"); cb.setChecked(True)
            cb.setProperty("cid", ch["id"])
            self.area.addWidget(cb); self.checks.append(cb)
        self.info.setText(f"Предложено к выходу: {len(leave)}. Отметь и подтверди.")
        self.confirm.setEnabled(True)

    def _leave(self):
        ids = [c.property("cid") for c in self.checks if c.isChecked()]
        if not ids:
            return
        if QMessageBox.question(self, "Подтверждение",
                f"Выйти из {len(ids)} каналов? Действие необратимо.") != QMessageBox.Yes:
            return
        try:
            fut = self.worker.submit(ChannelManager(self.worker.client).leave_channels(ids))
            res = fut.result(timeout=120)
            self.info.setText(f"Вышли: {len(res['left'])}, ошибок: {len(res['failed'])}")
        except Exception as e:
            self.info.setText(f"Ошибка: {e}")


class MainWindow(QMainWindow):
    def __init__(self, settings, db, ollama, persona, videos, worker, agent):
        super().__init__()
        self.settings, self.db, self.worker = settings, db, worker
        self.setWindowTitle("Nersiti"); self.resize(1040, 700)
        tabs = QTabWidget()

        self.chats = QListWidget()
        tabs.addTab(self.chats, "Чаты и каналы")
        tabs.addTab(ChannelsTab(worker, ollama), "Чистка каналов")
        self.video_tab = VideoTab(videos)
        tabs.addTab(self.video_tab, "Видео")

        sett = QWidget(); sl = QVBoxLayout(sett)
        sl.addWidget(QLabel(f"Архив: {settings.data_path}"))
        sl.addWidget(QLabel(f"Модель ИИ: {settings.ai.model} (Ollama)"))
        sl.addStretch(1)
        tabs.addTab(sett, "Настройки")
        self.setCentralWidget(tabs)

        self.chat = AiChat(agent)
        self.addDockWidget(Qt.RightDockWidgetArea, self.chat); self.chat.hide()
        tb = self.addToolBar("main")
        self.status = QLabel("  Telegram: подключение…  "); self.status.setObjectName("muted")
        tb.addWidget(self.status)
        ai_btn = QPushButton("💬 Ассистент")
        ai_btn.clicked.connect(lambda: self.chat.setVisible(not self.chat.isVisible()))
        tb.addWidget(ai_btn)

        self.timer = QTimer(self); self.timer.timeout.connect(self._tick); self.timer.start(3000)
        self._tick()

    def _tick(self):
        # статус воркера
        if self.worker.error:
            self.status.setText(f"  Telegram: {self.worker.error[:60]}  ")
        elif self.worker.ready.is_set():
            self.status.setText("  Telegram: подключён · архивация идёт  ")
        # обновить список чатов
        try:
            cur = self.chats.currentRow()
            self.chats.clear()
            for c in self.db.list_chats():
                self.chats.addItem(QListWidgetItem(c["title"] or str(c["chat_id"])))
            if self.chats.count() == 0:
                self.chats.addItem("Пока пусто — идёт первичная загрузка…")
            if cur >= 0:
                self.chats.setCurrentRow(min(cur, self.chats.count() - 1))
        except Exception:
            pass
        try:
            self.video_tab._refresh()
        except Exception:
            pass


def main() -> None:
    settings = load_settings()
    settings.ensure_dirs()
    db = Database(settings.db_path)
    videos = VideoManager(db, settings)
    ollama = OllamaClient(base_url=settings.ai.base_url, model=settings.ai.model)
    persona = Persona(settings.persona_path)

    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_QSS)

    dlg = PasswordDialog(settings.security.password_sha256)
    dlg.exec()
    if not dlg.ok:
        return

    worker = TgWorker(settings, db, videos, ollama=ollama, persona=persona)
    worker.start()

    from ..agent import Agent
    agent = Agent(settings, db, videos, ollama, persona, worker=worker)

    win = MainWindow(settings, db, ollama, persona, videos, worker, agent)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
