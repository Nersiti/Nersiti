"""Локальная веб-панель (FastAPI, 127.0.0.1, пароль DASHBOARD_PASSWORD).

Эндпоинты (docs/PLAN.md §10):
    GET  /                      список чатов; в каждой строке — тумблер/режимы
                                и КНОПКА «Архив чата» -> /chat/{id}/archive
    POST /chat/{id}/settings    сохранить настройки чата
    GET  /chat/{id}/archive     ПОЛНЫЙ архив переписки чата из локальной БД:
                                все сообщения (вх./исх.), удалённые (помечены),
                                версии правок, медиа-превью; пагинация + ?q=
    GET  /drafts                очередь черновиков
    POST /drafts/{id}/approve   отправить (опц. изменённый текст)
    POST /drafts/{id}/reject    отклонить
    GET  /search?q=             поиск по ВСЕМУ архиву (FTS5)
    POST /persona               редактирование persona.md
Данные архива берём из storage.db (get_chat_history), НЕ из Telegram.
TODO(исполнитель): Jinja2-шаблоны в templates/, стили в static/, без внешних CDN.
"""
# TODO
