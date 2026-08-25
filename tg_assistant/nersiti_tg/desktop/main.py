"""Nersiti Desktop — Windows-приложение (строгий чёрный стиль).

Возможности каркаса:
  - запрос пароля при каждом входе (SHA-256 из config.security);
  - строгая чёрная тема (QSS);
  - вкладки: Чаты/Каналы, Видео (дедуп + счётчики), Настройки;
  - скрытый ИИ-чат под иконкой (кнопка на панели инструментов).

Telegram-доступ (Telethon) подключается в блоке, помеченном TODO — он async и
требует qasync/поток; ВСЯ остальная логика работает in-process через модули
nersiti_tg (БД, видео, ИИ). Запуск:  python -m nersiti_tg.desktop.main

Требуется: pip install PySide6  (и httpx для ИИ-чата).
"""
from __future__ import annotations

import sys
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QDialog, QLineEdit, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QMainWindow, QWidget, QTabWidget, QListWidget, QTextEdit,
    QFileDialog, QDockWidget, QMessageBox,
)

from ..auth import check_password
from ..ai.ollama_client import OllamaClient
from ..ai.persona import Persona
from ..config import load_settings
from ..media.video_manager import VideoManager
from ..storage.db import Database


DARK_QSS = """
* { color: #e6e6e6; font-family: 'Segoe UI', sans-serif; font-size: 13px; }
QWidget { background: #0a0a0a; }
QMainWindow, QDialog { background: #060606; }
QLineEdit, QTextEdit, QListWidget {
    background: #111111; border: 1px solid #262626; border-radius: 8px;
    padding: 8px; selection-background-color: #333;
}
QLineEdit:focus, QTextEdit:focus { border: 1px solid #444; }
QPushButton {
    background: #161616; border: 1px solid #2a2a2a; border-radius: 8px;
    padding: 8px 14px;
}
QPushButton:hover { background: #1f1f1f; }
QPushButton#primary { background: #1c1c1c; border: 1px solid #3a3a3a; font-weight: 600; }
QTabWidget::pane { border: 1px solid #1c1c1c; }
QTabBar::tab {
    background: #0d0d0d; padding: 8px 16px; border: 1px solid #1c1c1c;
    border-bottom: none;
}
QTabBar::tab:selected { background: #161616; }
QLabel#title { font-size: 18px; font-weight: 700; }
QLabel#muted { color: #7a7a7a; }
QDockWidget::title { background: #0d0d0d; padding: 6px; }
"""


class PasswordDialog(QDialog):
    def __init__(self, expected_hash: str):
        super().__init__()
        self.expected_hash = expected_hash
        self.ok = False
        self.setWindowTitle("Nersiti — вход")
        self.setFixedWidth(360)
        lay = QVBoxLayout(self)
        title = QLabel("Nersiti"); title.setObjectName("title")
        sub = QLabel("Введите пароль"); sub.setObjectName("muted")
        self.inp = QLineEdit(); self.inp.setEchoMode(QLineEdit.Password)
        self.inp.setPlaceholderText("Пароль")
        self.inp.returnPressed.connect(self._try)
        btn = QPushButton("Войти"); btn.setObjectName("primary"); btn.clicked.connect(self._try)
        self.err = QLabel(""); self.err.setStyleSheet("color:#e0554a")
        for w in (title, sub, self.inp, self.err, btn):
            lay.addWidget(w)

    def _try(self):
        if check_password(self.inp.text(), self.expected_hash):
            self.ok = True
            self.accept()
        else:
            self.err.setText("Неверный пароль")
            self.inp.clear()


class AiChat(QDockWidget):
    """Скрытый ИИ-чат (dock). Открывается кнопкой на панели."""
    reply_ready = Signal(str)

    def __init__(self, ollama: OllamaClient, persona: Persona):
        super().__init__("ИИ-ассистент")
        self.ollama, self.persona = ollama, persona
        self.reply_ready.connect(self._show_reply)
        body = QWidget(); lay = QVBoxLayout(body)
        self.log = QTextEdit(); self.log.setReadOnly(True)
        row = QHBoxLayout()
        self.inp = QLineEdit(); self.inp.setPlaceholderText("Спросить ассистента…")
        self.inp.returnPressed.connect(self._send)
        send = QPushButton("→"); send.clicked.connect(self._send)
        row.addWidget(self.inp); row.addWidget(send)
        lay.addWidget(self.log); lay.addLayout(row)
        self.setWidget(body)

    def _send(self):
        q = self.inp.text().strip()
        if not q:
            return
        self.log.append(f"<b>Вы:</b> {q}")
        self.inp.clear()
        threading.Thread(target=self._ask, args=(q,), daemon=True).start()

    def _ask(self, q: str):
        import asyncio
        try:
            msg = asyncio.run(self.ollama.chat(
                [{"role": "system", "content": self.persona.get()},
                 {"role": "user", "content": q}]))
            text = (msg or {}).get("content", "") or "[модель не подключена]"
        except Exception as e:
            text = f"[ИИ недоступен: {e}]"
        self.reply_ready.emit(text)

    def _show_reply(self, text: str):
        self.log.append(f"<b>Ассистент:</b> {text}")


class VideoTab(QWidget):
    def __init__(self, videos: VideoManager):
        super().__init__()
        self.videos = videos
        lay = QVBoxLayout(self)
        self.stats = QLabel(); self.stats.setObjectName("muted")
        drop = QPushButton("Скинуть видео (файлы)"); drop.setObjectName("primary")
        drop.clicked.connect(self._drop)
        dedup = QPushButton("Найти и удалить дубли в папке…")
        dedup.clicked.connect(self._dedup)
        for w in (QLabel("Видео: дедупликация и подсчёт"), drop, dedup, self.stats):
            lay.addWidget(w)
        lay.addStretch(1)
        self._refresh()

    def _refresh(self):
        s = self.videos.stats()
        self.stats.setText(
            f"Скинуто видео: {s['dropped_videos']} · Уникальных: {s['unique']} · "
            f"Пропущено дублей: {s['duplicate_skipped']} · Удалено дублей: {s['duplicates_removed']}")

    def _drop(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Выбрать видео")
        for f in files:
            self.videos.drop_video(f)
        self._refresh()

    def _dedup(self):
        folder = QFileDialog.getExistingDirectory(self, "Папка с видео")
        if folder:
            rep = self.videos.dedup_folder(folder)
            QMessageBox.information(self, "Дедупликация",
                                    f"Удалено дублей: {rep['removed_count']}, "
                                    f"освобождено: {rep['freed_bytes']} байт")
            self._refresh()


class MainWindow(QMainWindow):
    def __init__(self, settings, db: Database, ollama: OllamaClient, persona: Persona):
        super().__init__()
        self.setWindowTitle("Nersiti")
        self.resize(1000, 680)
        tabs = QTabWidget()

        chats = QListWidget()
        for c in db.list_chats():
            chats.addItem(f'{c["title"] or c["chat_id"]}')
        if chats.count() == 0:
            chats.addItem("Пока пусто — подключи Telegram (Telethon).")
        tabs.addTab(chats, "Чаты и каналы")

        self.videos = VideoManager(db, settings)
        tabs.addTab(VideoTab(self.videos), "Видео")

        sett = QWidget(); sl = QVBoxLayout(sett)
        sl.addWidget(QLabel(f"Архив: {settings.data_path}"))
        sl.addWidget(QLabel("Пароль входа задаётся в config.security."))
        sl.addStretch(1)
        tabs.addTab(sett, "Настройки")

        self.setCentralWidget(tabs)

        # скрытый ИИ-чат под иконкой на панели
        self.chat = AiChat(ollama, persona)
        self.addDockWidget(Qt.RightDockWidgetArea, self.chat)
        self.chat.hide()
        tb = self.addToolBar("main")
        ai_btn = QPushButton("💬 Ассистент")
        ai_btn.clicked.connect(lambda: self.chat.setVisible(not self.chat.isVisible()))
        tb.addWidget(ai_btn)

        # TODO(Telegram): здесь поднять Telethon-клиент (qasync), заполнить чаты/каналы,
        # включить архивацию, ChannelManager (чистка каналов по промту),
        # приём/скидывание видео из чатов в VideoManager.


def main() -> None:
    settings = load_settings()
    settings.ensure_dirs()
    db = Database(settings.db_path)
    ollama = OllamaClient(base_url=settings.ai.base_url, model=settings.ai.model)
    persona = Persona(settings.persona_path)

    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_QSS)

    dlg = PasswordDialog(settings.security.password_sha256)
    dlg.exec()
    if not dlg.ok:
        return

    win = MainWindow(settings, db, ollama, persona)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
