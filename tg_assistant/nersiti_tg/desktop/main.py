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

from PySide6.QtCore import Qt, QTimer, QObject, Signal, QSize
from PySide6.QtWidgets import (
    QApplication, QDialog, QLineEdit, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QMainWindow, QWidget, QTabWidget, QListWidget, QListWidgetItem,
    QTextEdit, QFileDialog, QDockWidget, QMessageBox, QCheckBox, QScrollArea,
    QMenu, QSizePolicy,
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
* { color:#e8eaed; font-family:'Segoe UI',sans-serif; font-size:13px; }
QWidget { background:#0b0c0e; }
QMainWindow, QDialog { background:#08090b; }

QTabWidget::pane { border:none; background:#0b0c0e; top:-1px; }
QTabBar { background:transparent; qproperty-drawBase:0; }
QTabBar::tab { background:transparent; color:#868c96; padding:11px 20px; margin-right:2px;
  border:none; border-bottom:2px solid transparent; font-weight:600; }
QTabBar::tab:selected { color:#f0f2f5; border-bottom:2px solid #5b8dd6; }
QTabBar::tab:hover { color:#c5c9d1; }

QListWidget { background:#0e1013; border:1px solid #1b1e23; border-radius:12px; padding:6px; outline:0; }
QListWidget::item { padding:12px 14px; border-radius:9px; margin:1px 2px; color:#d6dae1; }
QListWidget::item:hover { background:#15181d; }
QListWidget::item:selected { background:#1a2634; color:#eaf1fb; }

QLineEdit, QTextEdit { background:#0e1013; border:1px solid #1f2329; border-radius:10px;
  padding:10px 12px; color:#e8eaed; selection-background-color:#2f4a63; }
QLineEdit:focus, QTextEdit:focus { border:1px solid #3a5a7a; }
QLineEdit::placeholder { color:#5c626c; }

QScrollArea { background:#0b0c0e; border:none; }

QPushButton { background:#16181c; border:1px solid #262a30; border-radius:9px;
  padding:9px 15px; color:#d6dae1; }
QPushButton:hover { background:#1d2025; border-color:#31363d; }
QPushButton#primary { background:#213445; border:1px solid #305777; color:#e0ecf9; font-weight:600; }
QPushButton#primary:hover { background:#274257; }
QPushButton:checked { background:#213445; border-color:#305777; color:#e0ecf9; }
QPushButton#danger { background:#2a1918; border:1px solid #5a2f2a; color:#e88b80; }
QPushButton#danger:hover { background:#331d1b; }

QToolBar { background:#090a0c; border-bottom:1px solid #191c21; spacing:10px; padding:8px 12px; }
QToolBar QLabel { color:#7c828c; }

QDockWidget { border:none; titlebar-close-icon:none; }
QDockWidget::title { background:#0d0f12; padding:10px 14px; color:#868c96; border-bottom:1px solid #191c21; }

QLabel#title { font-size:22px; font-weight:700; color:#f2f4f7; }
QLabel#h { font-size:16px; font-weight:700; color:#eef1f5; }
QLabel#muted { color:#7c828c; }
QCheckBox { spacing:9px; padding:6px 2px; color:#d6dae1; }
QCheckBox::indicator { width:16px; height:16px; border:1px solid #3a3f47; border-radius:4px; background:#0e1013; }
QCheckBox::indicator:checked { background:#5b8dd6; border-color:#5b8dd6; }

QScrollBar:vertical { background:transparent; width:11px; margin:3px; }
QScrollBar::handle:vertical { background:#2a2e35; border-radius:5px; min-height:32px; }
QScrollBar::handle:vertical:hover { background:#3a3f47; }
QScrollBar:horizontal { background:transparent; height:11px; margin:3px; }
QScrollBar::handle:horizontal { background:#2a2e35; border-radius:5px; min-width:32px; }
QScrollBar::add-line, QScrollBar::sub-line { width:0; height:0; }
QScrollBar::add-page, QScrollBar::sub-page { background:transparent; }
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
    dialogs = Signal(list)
    html = Signal(str)
    append = Signal(str)


AVATAR_COLORS = ["#5b8dd6", "#c96a5e", "#7bb67f", "#b98bd0", "#d0a24a",
                 "#5aa9a0", "#c77fa0", "#8f9bd6"]


def _initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[1][0]).upper()


class ChatRow(QWidget):
    """Строка чата как в Telegram: аватар-инициалы, имя, превью, непрочитанные, «⋯»."""
    def __init__(self, d: dict, menu_cb):
        super().__init__()
        self.setFixedHeight(60)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay = QHBoxLayout(self); lay.setContentsMargins(8, 6, 8, 6); lay.setSpacing(11)
        av = QLabel(_initials(d["name"])); av.setFixedSize(44, 44); av.setAlignment(Qt.AlignCenter)
        col = "#3a6ea5" if d["type"] == "saved" else AVATAR_COLORS[d["id"] % len(AVATAR_COLORS)]
        av.setStyleSheet(f"background:{col};border-radius:22px;color:#fff;font-weight:700;font-size:15px;")
        lay.addWidget(av)
        mid = QVBoxLayout(); mid.setSpacing(2); mid.setContentsMargins(0, 0, 0, 0)
        name = QLabel(d["name"]); name.setStyleSheet("font-weight:600;font-size:14px;color:#eef1f5;")
        name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        prev = QLabel(d.get("preview") or " "); prev.setStyleSheet("color:#818892;font-size:12px;")
        prev.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        mid.addWidget(name); mid.addWidget(prev)
        lay.addLayout(mid, 1)
        if d.get("unread"):
            badge = QLabel(str(d["unread"])); badge.setAlignment(Qt.AlignCenter)
            badge.setStyleSheet("background:#5b8dd6;color:#fff;border-radius:9px;"
                                "padding:1px 7px;font-size:11px;font-weight:700;")
            lay.addWidget(badge)
        dots = QPushButton("⋯"); dots.setFixedSize(30, 30)
        dots.clicked.connect(lambda: menu_cb(d, dots))
        lay.addWidget(dots)


class ConversationDialog(QDialog):
    """Окно переписки: история + отправка сообщений."""
    def __init__(self, d, worker):
        super().__init__()
        self.d, self.worker = d, worker
        self.setWindowTitle(d["name"]); self.resize(560, 640)
        self.bus = Bus()
        self.bus.html.connect(self._set_html); self.bus.append.connect(self._append)
        lay = QVBoxLayout(self); lay.setContentsMargins(14, 14, 14, 14); lay.setSpacing(10)
        hd = QLabel(d["name"]); hd.setObjectName("h"); lay.addWidget(hd)
        self.view = QTextEdit(); self.view.setReadOnly(True); lay.addWidget(self.view, 1)
        row = QHBoxLayout(); row.setSpacing(8)
        self.inp = QLineEdit(); self.inp.setPlaceholderText("Сообщение…")
        self.inp.returnPressed.connect(self._send)
        snd = QPushButton("Отправить"); snd.setObjectName("primary"); snd.clicked.connect(self._send)
        row.addWidget(self.inp); row.addWidget(snd); lay.addLayout(row)
        self.view.setHtml("<div style='color:#818892'>Загружаю переписку…</div>")
        threading.Thread(target=self._load, daemon=True).start()

    def _bubble(self, m):
        align = "right" if m["out"] else "left"
        bg = "#182634" if m["out"] else "#141719"
        text = (m["text"] or "").replace("<", "&lt;").replace("\n", "<br>")
        return (f"<div style='text-align:{align};margin:5px 0'><span style='background:{bg};"
                f"padding:7px 11px;border-radius:9px;display:inline-block;max-width:75%'>{text}</span></div>")

    def _load(self):
        try:
            msgs = self.worker.submit(self.worker.get_history(self.d["id"], 60)).result(timeout=40)
            self.bus.html.emit("".join(self._bubble(m) for m in msgs) or
                               "<div style='color:#818892'>Пусто</div>")
        except Exception as e:  # noqa
            self.bus.html.emit(f"<div style='color:#c96a5e'>Не удалось загрузить: {e}</div>")

    def _set_html(self, html):
        self.view.setHtml(html)
        self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())

    def _append(self, html):
        self.view.append(html)

    def _send(self):
        t = self.inp.text().strip()
        if not t:
            return
        self.inp.clear()
        self.view.append(self._bubble({"out": True, "text": t}))
        threading.Thread(target=self._send_bg, args=(t,), daemon=True).start()

    def _send_bg(self, t):
        try:
            self.worker.submit(self.worker.send_message(self.d["id"], t)).result(timeout=40)
        except Exception as e:  # noqa
            self.bus.append.emit(f"<div style='color:#c96a5e'>Не отправлено: {e}</div>")


class ChatsTab(QWidget):
    CATS = [("all", "Все"), ("user", "Личные"), ("group", "Группы"),
            ("channel", "Каналы"), ("saved", "Избранное")]

    def __init__(self, worker, db, on_send_to_ai):
        super().__init__()
        self.worker = worker
        self.db = db
        self.on_send_to_ai = on_send_to_ai
        self.category = "all"
        self.query = ""
        self.dialogs = []
        self._sig = None
        self.bus = Bus(); self.bus.dialogs.connect(self._render)
        lay = QVBoxLayout(self); lay.setContentsMargins(18, 16, 18, 16); lay.setSpacing(10)
        head = QLabel("Чаты"); head.setObjectName("h"); lay.addWidget(head)

        chips = QHBoxLayout(); chips.setSpacing(6)
        self.cat_btns = {}
        for key, label in self.CATS:
            b = QPushButton(label); b.setCheckable(True); b.setChecked(key == "all")
            b.clicked.connect(lambda _=False, k=key: self._set_cat(k))
            self.cat_btns[key] = b; chips.addWidget(b)
        chips.addStretch(1)
        lay.addLayout(chips)

        self.search = QLineEdit(); self.search.setPlaceholderText("Поиск по чатам…")
        self.search.textChanged.connect(self._on_search)
        lay.addWidget(self.search)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._open_chat)
        lay.addWidget(self.list, 1)
        self.hint = QLabel("Загружаю список чатов…  (двойной клик — открыть чат)")
        self.hint.setObjectName("muted"); lay.addWidget(self.hint)

        self.timer = QTimer(self); self.timer.timeout.connect(self._fetch); self.timer.start(12000)
        QTimer.singleShot(1500, self._fetch)

    def _set_cat(self, key):
        self.category = key
        for k, b in self.cat_btns.items():
            b.setChecked(k == key)
        self._sig = None; self._apply()

    def _on_search(self, text):
        self.query = text.strip().lower(); self._sig = None; self._apply()

    def _fetch(self):
        if not self.worker.ready.is_set() or self.worker.error:
            return
        threading.Thread(target=self._fetch_bg, daemon=True).start()

    def _fetch_bg(self):
        try:
            res = self.worker.submit(self.worker.list_dialogs()).result(timeout=40)
            self.bus.dialogs.emit(res)
        except Exception:
            pass

    def _render(self, dialogs):
        self.dialogs = dialogs; self._apply()

    def _apply(self):
        rows = [d for d in self.dialogs
                if (self.category == "all" or d["type"] == self.category)
                and (not self.query or self.query in d["name"].lower())]
        sig = tuple((d["id"], d["unread"], d["preview"]) for d in rows)
        if sig == self._sig:        # не пересобирать без изменений (убирает мигание)
            return
        self._sig = sig
        self.list.clear()
        for d in rows:
            item = QListWidgetItem(); item.setSizeHint(QSize(0, 60))
            item.setData(Qt.UserRole, d)
            self.list.addItem(item)
            self.list.setItemWidget(item, ChatRow(d, self._menu))
        self.hint.setText(f"{len(rows)} чатов  ·  двойной клик — открыть, ⋯ — меню")

    def _open_chat(self, item):
        d = item.data(Qt.UserRole)
        if d:
            ConversationDialog(d, self.worker).exec()

    def _menu(self, d, btn):
        m = QMenu(self)
        a_off = m.addAction("Автоответ: выкл")
        a_draft = m.addAction("Автоответ: черновик")
        a_gen = m.addAction("Автоответ: авто — сгенерировать")
        a_dlg = m.addAction("Автоответ: авто — вести диалог")
        m.addSeparator()
        a_open = m.addAction("Открыть чат")
        a_ai = m.addAction("Переслать в нейросеть")
        act = m.exec(btn.mapToGlobal(btn.rect().bottomLeft()))
        if act is None:
            return
        from ..storage.models import ChatSettings
        if act == a_off:
            self._set_ar(d, "off", "generate")
        elif act == a_draft:
            self._set_ar(d, "draft", "generate")
        elif act == a_gen:
            self._set_ar(d, "auto", "generate")
        elif act == a_dlg:
            self._set_ar(d, "auto", "dialogue")
        elif act == a_open:
            ConversationDialog(d, self.worker).exec()
        elif act == a_ai:
            self.on_send_to_ai(d)

    def _set_ar(self, d, mode, submode):
        from ..storage.models import ChatSettings
        self.db.set_chat_settings(ChatSettings(chat_id=d["id"], mode=mode,
                                               auto_submode=submode, enabled=1))
        self.hint.setText(f"Автоответ для «{d['name']}» → {mode}" +
                          (f" ({submode})" if mode == "auto" else ""))


# слова-триггеры действий: только тогда запускаем агента с инструментами
ACTION_WORDS = ("отправ", "видео", "автоответ", "ответь", "почист", "чист",
                "канал", "дедуп", "дубл", "найди", "поиск", "ищи", "удали",
                "статистик", "счётчик", "счетчик", "напиши", "сообщени",
                "id=", "чат:")


def _needs_tools(text: str) -> bool:
    t = text.lower()
    return any(w in t for w in ACTION_WORDS)


class AiChat(QDockWidget):
    def __init__(self, agent):
        super().__init__("ИИ-ассистент")
        self.agent = agent
        self.history = []   # память разговора: [{role, content}, ...]
        self.bus = Bus(); self.bus.text.connect(self._show)
        body = QWidget(); body.setStyleSheet("background:#0b0c0e;")
        lay = QVBoxLayout(body); lay.setContentsMargins(12, 12, 12, 12); lay.setSpacing(10)
        self.log = QTextEdit(); self.log.setReadOnly(True)
        self.log.setStyleSheet("border:1px solid #1b1e23; background:#0e1013;")
        self.status = QLabel(""); self.status.setObjectName("muted")
        row = QHBoxLayout(); row.setSpacing(8)
        self.inp = QLineEdit()
        self.inp.setPlaceholderText("Напиши, что сделать: отправь видео, включи автоответ, найди…")
        self.inp.returnPressed.connect(self._send)
        snd = QPushButton("→"); snd.setObjectName("primary"); snd.setFixedWidth(46)
        snd.clicked.connect(self._send)
        row.addWidget(self.inp); row.addWidget(snd)
        lay.addWidget(self.log, 1); lay.addWidget(self.status); lay.addLayout(row)
        self.setWidget(body)
        self._hello()

    def _hello(self):
        self.log.append(
            "<div style='color:#7c828c;padding:6px 2px'>Привет! Я ассистент Nersiti. "
            "Могу: найти в переписке, включить автоответ, отправить видео, "
            "предложить чистку каналов. Просто напиши задачу.</div>")

    def _send(self):
        q = self.inp.text().strip()
        if not q:
            return
        self.log.append(
            f"<div style='margin:8px 0'><span style='color:#5b8dd6;font-weight:600'>Вы</span>"
            f"<div style='background:#182634;border-radius:10px;padding:8px 11px;margin-top:3px'>{q}</div></div>")
        self.inp.clear()
        self.status.setText("Ассистент печатает…")
        threading.Thread(target=self._ask, args=(q,), daemon=True).start()

    def _ask(self, q: str):
        try:
            hist = list(self.history)
            if _needs_tools(q):
                answer = asyncio.run(self.agent.run(q, history=hist))
            else:
                answer = asyncio.run(self.agent.chat_simple(q, history=hist))
            answer = answer or "готово"
            # запомнить обмен (ограничим память последними 16 репликами)
            self.history.append({"role": "user", "content": q})
            self.history.append({"role": "assistant", "content": answer})
            self.history = self.history[-16:]
            self.bus.text.emit(answer)
        except Exception as e:  # noqa
            self.bus.text.emit(
                "⚠ Не удалось ответить. Проверь, что запущена Ollama и скачана "
                f"модель (ollama pull qwen2.5:7b-instruct).\nПодробно: {e}")

    def _show(self, text: str):
        self.status.setText("")
        safe = text.replace("<", "&lt;").replace("\n", "<br>")
        self.log.append(
            f"<div style='margin:8px 0'><span style='color:#7bb67f;font-weight:600'>Ассистент</span>"
            f"<div style='background:#141719;border:1px solid #1f2329;border-radius:10px;"
            f"padding:8px 11px;margin-top:3px'>{safe}</div></div>")


class VideoTab(QWidget):
    def __init__(self, videos: VideoManager):
        super().__init__()
        self.videos = videos
        lay = QVBoxLayout(self); lay.setContentsMargins(18, 16, 18, 16); lay.setSpacing(11)
        head = QLabel("Видео — дубли и подсчёт"); head.setObjectName("h")
        self.stats = QLabel(); self.stats.setObjectName("muted")
        drop = QPushButton("Скинуть видео (файлы)"); drop.setObjectName("primary"); drop.clicked.connect(self._drop)
        dedup = QPushButton("Найти и удалить дубли в папке…"); dedup.clicked.connect(self._dedup)
        row = QHBoxLayout(); row.setSpacing(8); row.addWidget(drop); row.addWidget(dedup); row.addStretch(1)
        self.vlist = QListWidget()
        for w in (head, self.stats):
            lay.addWidget(w)
        lay.addLayout(row)
        lay.addWidget(QLabel("Сохранённые видео:"))
        lay.addWidget(self.vlist, 1)
        self._refresh()

    def _refresh(self):
        s = self.videos.stats()
        self.stats.setText(
            f"Скинуто: {s['dropped_videos']} · Уникальных: {s['unique']} · "
            f"Пропущено дублей: {s['duplicate_skipped']} · Удалено дублей: {s['duplicates_removed']}")
        # список файлов в папке видео
        try:
            files = sorted(self.videos.saved_dir.glob("*"))
            if self.vlist.count() != len([f for f in files if f.is_file()]):
                self.vlist.clear()
                for f in files:
                    if f.is_file():
                        self.vlist.addItem(f.name)
        except Exception:
            pass

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
        lay = QVBoxLayout(self); lay.setContentsMargins(18, 16, 18, 16); lay.setSpacing(10)
        _hh = QLabel("Чистка каналов по промту"); _hh.setObjectName("h")
        lay.addWidget(_hh)
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

        tabs.addTab(ChatsTab(worker, db, self._send_to_ai), "Чаты")
        tabs.addTab(ChannelsTab(worker, ollama), "Чистка каналов")
        self.video_tab = VideoTab(videos)
        tabs.addTab(self.video_tab, "Видео")

        sett = QWidget(); sl = QVBoxLayout(sett)
        sl.setContentsMargins(18, 16, 18, 16); sl.setSpacing(9)
        _sh = QLabel("Настройки"); _sh.setObjectName("h"); sl.addWidget(_sh)
        m1 = QLabel(f"Папка архива:  {settings.data_path}"); m1.setObjectName("muted")
        m2 = QLabel(f"Модель ИИ:  {settings.ai.model} (Ollama)"); m2.setObjectName("muted")
        m3 = QLabel("Пароль входа задаётся в config (по умолчанию Logingood123337)."); m3.setObjectName("muted")
        for w in (m1, m2, m3):
            sl.addWidget(w)
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
        if self.worker.error:
            self.status.setText(f"  Telegram: {self.worker.error[:60]}  ")
        elif self.worker.ready.is_set():
            self.status.setText("  Telegram: подключён · архивация идёт  ")
        else:
            self.status.setText("  Telegram: подключение…  ")
        try:
            self.video_tab._refresh()
        except Exception:
            pass

    def _send_to_ai(self, d):
        """«Переслать в нейросеть»: открыть ассистента и подставить id чата в ввод."""
        self.chat.show(); self.chat.raise_()
        self.chat.inp.setText(f"[чат: {d['name']} | id={d['id']}] ")
        self.chat.inp.setFocus()


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
