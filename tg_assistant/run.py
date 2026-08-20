"""Точка входа Nersiti TG Assistant.

Порядок (docs/PLAN.md §11):
  1) load_settings() из .env + config.yaml
  2) setup_logging(); init_db(); создать папки data/
  3) build_client() -> авторизация Telethon (интерактивно при первом запуске)
  4) handlers.register(client, deps)  -> архив + автоответ
  5) поднять FastAPI (uvicorn) и Telethon в одном asyncio loop (asyncio.gather)
  6) корректное завершение по Ctrl+C

TODO(исполнитель): реализовать по контрактам модулей.
"""
# TODO


if __name__ == "__main__":
    # TODO: asyncio.run(main())
    raise SystemExit("Не реализовано. См. docs/PLAN.md и заполните модули.")
