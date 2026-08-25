"""Загрузка настроек: .env (секреты) + config.yaml (поведение).

Все пути данных строятся от storage.data_dir. Для локального запуска и тестов
есть разумные значения по умолчанию, поэтому сервер стартует и без config.yaml.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

try:
    import yaml  # PyYAML
except Exception:  # pragma: no cover
    yaml = None


@dataclass
class AISettings:
    provider: str = "ollama"
    base_url: str = "http://127.0.0.1:11434"
    model: str = "qwen2.5:7b-instruct"
    embed_model: str = "bge-m3"
    temperature: float = 0.7
    max_tokens: int = 512
    context_messages: int = 20
    use_tools: bool = True
    # ассистент: "auto" (Claude если есть ключ, иначе Ollama) | "claude" | "ollama"
    assistant_backend: str = "auto"
    claude_model: str = "claude-opus-5"   # можно claude-sonnet-5 / claude-haiku-4-5 (дешевле/быстрее)


@dataclass
class WebSettings:
    enabled: bool = True
    search_provider: str = "duckduckgo"
    searxng_url: str = "http://127.0.0.1:8080"
    tavily_api_key: str = ""
    max_results: int = 5
    fetch_timeout_sec: int = 15


@dataclass
class ArchiveSettings:
    save_media: bool = True
    save_deleted: bool = True
    save_edits: bool = True


@dataclass
class AutoreplySettings:
    default_mode: str = "off"            # off | draft | auto
    default_auto_submode: str = "generate"  # preset | generate | dialogue
    default_preset_text: str = "Привет! Отвечу чуть позже."
    min_delay_sec: int = 3
    max_delay_sec: int = 12
    typing_simulation: bool = True


@dataclass
class StorageSettings:
    # По умолчанию архив в домашней папке пользователя (Windows: C:\Users\<имя>\NersitiArchive)
    data_dir: str = str(Path.home() / "NersitiArchive")


@dataclass
class SecuritySettings:
    # SHA-256 пароля входа. По умолчанию — хэш "Logingood123337".
    password_sha256: str = "5e05dd45cf5f98725ed53a5a230197c4bfe664d7bf871d75bcb68a83f29239ca"


@dataclass
class VideoSettings:
    # Дедупликация одинаковых видео (по хэшу) и чистка дублей.
    delete_duplicates: bool = True        # удалять дубликаты, оставляя один
    near_duplicates: bool = False         # искать похожие (не только точные копии)
    saved_folder: str = "videos"          # подпапка архива для «скинутых» видео


@dataclass
class Secrets:
    tg_api_id: int = 0
    tg_api_hash: str = ""
    dashboard_password: str = "change_me"
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 8765
    sync_token: str = "change_me"
    anthropic_api_key: str = ""   # ключ Claude (ANTHROPIC_API_KEY) — включает ИИ-ассистента Claude


@dataclass
class Settings:
    storage: StorageSettings = field(default_factory=StorageSettings)
    ai: AISettings = field(default_factory=AISettings)
    web: WebSettings = field(default_factory=WebSettings)
    archive: ArchiveSettings = field(default_factory=ArchiveSettings)
    autoreply: AutoreplySettings = field(default_factory=AutoreplySettings)
    security: SecuritySettings = field(default_factory=SecuritySettings)
    video: VideoSettings = field(default_factory=VideoSettings)
    secrets: Secrets = field(default_factory=Secrets)

    # --- производные пути ---
    @property
    def data_path(self) -> Path:
        return Path(self.storage.data_dir).expanduser()

    @property
    def db_path(self) -> Path:
        return self.data_path / "archive.db"

    @property
    def media_dir(self) -> Path:
        return self.data_path / "media"

    @property
    def video_dir(self) -> Path:
        return self.data_path / "videos"

    @property
    def persona_path(self) -> Path:
        return self.data_path / "persona.md"

    @property
    def log_path(self) -> Path:
        return self.data_path / "app.log"

    def ensure_dirs(self) -> None:
        self.data_path.mkdir(parents=True, exist_ok=True)
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self.video_dir.mkdir(parents=True, exist_ok=True)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("secrets", None)  # секреты не отдаём наружу
        return d


def _load_env(env_path: str) -> None:
    """Мини-парсер .env (без внешних зависимостей). Не перетирает уже заданные."""
    p = Path(env_path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if key and key not in os.environ:
            os.environ[key] = val


def _apply_yaml(settings: Settings, data: dict[str, Any]) -> None:
    for section_name in ("storage", "ai", "web", "archive", "autoreply",
                          "security", "video"):
        section = data.get(section_name)
        if not isinstance(section, dict):
            continue
        obj = getattr(settings, section_name)
        for k, v in section.items():
            if hasattr(obj, k):
                setattr(obj, k, v)


def load_settings(env_path: str = ".env", yaml_path: str = "config.yaml") -> Settings:
    _load_env(env_path)
    settings = Settings()

    if yaml is not None:
        p = Path(yaml_path)
        if p.exists():
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            _apply_yaml(settings, data)

    s = settings.secrets
    s.tg_api_id = int(os.environ.get("TG_API_ID", s.tg_api_id) or 0)
    s.tg_api_hash = os.environ.get("TG_API_HASH", s.tg_api_hash)
    s.dashboard_password = os.environ.get("DASHBOARD_PASSWORD", s.dashboard_password)
    s.dashboard_host = os.environ.get("DASHBOARD_HOST", s.dashboard_host)
    s.dashboard_port = int(os.environ.get("DASHBOARD_PORT", s.dashboard_port) or 8765)
    s.sync_token = os.environ.get("SYNC_TOKEN", s.sync_token)
    s.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", s.anthropic_api_key)

    # переопределение каталога данных из окружения (удобно для тестов)
    if os.environ.get("NERSITI_DATA_DIR"):
        settings.storage.data_dir = os.environ["NERSITI_DATA_DIR"]

    return settings
