"""Локальная веб-панель (FastAPI, 127.0.0.1, пароль DASHBOARD_PASSWORD).

Эндпоинты (docs/PLAN.md §10):
    GET  /                      список чатов + тумблеры/режимы
    POST /chat/{id}/settings    сохранить настройки чата
    GET  /drafts                очередь черновиков
    POST /drafts/{id}/approve   отправить (опц. изменённый текст)
    POST /drafts/{id}/reject    отклонить
    GET  /search?q=             поиск по архиву (FTS5)
    GET  /chat/{id}/history     история из архива
    POST /persona               редактирование persona.md
TODO(исполнитель): Jinja2-шаблоны в templates/, стили в static/, без внешних CDN.
"""
# TODO
