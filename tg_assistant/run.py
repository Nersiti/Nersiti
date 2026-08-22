"""Точка входа бэкенда Nersiti (мозг на ПК).

Поднимает FastAPI-сервер с sync-API для мод-клиента и API панели.
Нейросеть (Ollama) подключается автоматически, когда запущена; до этого
сервер работает (архив, приём с телефона, preset-автоответы).

Запуск:  python run.py
"""
from __future__ import annotations

import uvicorn

from nersiti_tg.ai.ollama_client import OllamaClient
from nersiti_tg.ai.persona import Persona
from nersiti_tg.config import load_settings
from nersiti_tg.dashboard.app import create_app
from nersiti_tg.logging_setup import setup_logging
from nersiti_tg.storage.db import Database


def build():
    settings = load_settings()
    settings.ensure_dirs()
    setup_logging("INFO", settings.log_path)
    db = Database(settings.db_path)
    ollama = OllamaClient(base_url=settings.ai.base_url, model=settings.ai.model,
                          embed_model=settings.ai.embed_model,
                          temperature=settings.ai.temperature,
                          max_tokens=settings.ai.max_tokens)
    persona = Persona(settings.persona_path)
    app = create_app(settings, db, ollama, persona)
    return settings, app


def main() -> None:
    settings, app = build()
    uvicorn.run(app, host=settings.secrets.dashboard_host,
                port=settings.secrets.dashboard_port)


if __name__ == "__main__":
    main()
