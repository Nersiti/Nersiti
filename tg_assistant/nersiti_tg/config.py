"""Загрузка настроек: .env (секреты) + config.yaml (поведение).

Контракт:
    class Settings(pydantic.BaseModel) с полями по разделам PLAN.md §4.
    def load_settings(env_path=".env", yaml_path="config.yaml") -> Settings

TODO(исполнитель): реализовать через pydantic-settings + PyYAML.
Секреты (TG_API_ID/HASH, DASHBOARD_*) — только из окружения/.env.
"""
# TODO: реализация по docs/PLAN.md §4
