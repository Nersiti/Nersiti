# ПЛАН / ТЗ проекта «Nersiti TG Assistant»

> Это документ-задание для модели-исполнителя. Здесь описано ЧТО и КАК
> должно работать по каждому модулю: контракты функций, форматы данных,
> порядок вызовов. Исполнителю нужно только написать реализацию по этим
> контрактам — архитектура и решения уже приняты. Не менять структуру
> без причины. Все комментарии и строки — на русском.

## 0. Что это

Локальный софт, который работает «поверх» личного аккаунта Telegram:
- логинится как пользователь (userbot, MTProto/Telethon);
- имеет доступ ко всем чатам, истории, фото/видео/файлам;
- сохраняет КАЖДОЕ сообщение и КАЖДЫЙ файл в локальный архив
  (SQLite + FTS5 + папка media/), включая изменённые и удалённые;
- умеет отвечать за пользователя с помощью ЛОКАЛЬНОЙ модели (Ollama);
- управляется через локальную веб-панель (FastAPI) на localhost.

ВАЖНО ПО ПРИОРИТЕТАМ: ядро продукта — сам Telegram-софт (архив всего +
управление + автоответ). Нейросеть — ПОДКЛЮЧАЕМЫЙ модуль-помощник, а не
центр системы. Архив и панель должны работать даже если модель выключена.

Мозг — локальный (Ollama), НО с доступом в интернет через инструменты
(web_search / web_fetch, см. §7a). Веса модели — локальные; наружу уходят
только веб-запросы, которые модель делает осознанно через инструменты.

ГДЕ ХРАНИТСЯ ВСЁ: корень данных задаётся в config `storage.data_dir` и
указывает на ОТДЕЛЬНЫЙ диск ПК пользователя (напр. `D:/nersiti_data`).
Везде ниже, где написано `data/...`, подразумевается `storage.data_dir/...`.
Все пути (БД, media, сессия, persona.md, логи) строятся от этого корня.

## 1. Железо и модель (ограничения, из них всё вытекает)

Целевое железо: RTX 5060 (8 GB VRAM), 16 GB RAM, Ryzen 5 5500.
- Инференс: одна квантованная модель 7–8B, Q4_K_M (~5 GB) — влезает в VRAM.
  Рекомендуемые модели в Ollama (на выбор пользователя):
  - `owl/t-lite` или `qwen2.5:7b-instruct` — хорошо по-русски, «мягкая» цензура;
  - `dolphin-mistral:7b` — «без ограничений» (uncensored);
  - `saiga`-варианты — заточены под русский.
  Модель задаётся в config (`ai.model`), софт её не хардкодит.
- Эмбеддинги (для семантического поиска/памяти): `bge-m3` или
  `intfloat/multilingual-e5-small` — крутятся на CPU, VRAM не трогают.
- ОБУЧЕНИЕ НЕ ТРЕБУЕТСЯ. Берём ГОТОВУЮ модель из реестра Ollama и просто
  подключаем её. Установка — скриптом scripts/setup_model.(ps1|sh), который
  делает `ollama pull qwen2.5:7b-instruct` и `ollama pull bge-m3` на ПК
  пользователя. Дефолт зафиксирован: `ai.model = qwen2.5:7b-instruct`.

## 2. Технологический стек

- Python 3.11
- Telethon (userbot, MTProto)
- Ollama (локальный LLM-сервер, HTTP на 127.0.0.1:11434)
- SQLite + FTS5 (архив + полнотекстовый поиск), модуль sqlite3 из stdlib
- FastAPI + Uvicorn (веб-панель), Jinja2 (шаблоны)
- httpx (запросы к Ollama и web_fetch)
- pydantic / pydantic-settings (конфиг)
- PyYAML (per-chat настройки)
- ddgs (поиск DuckDuckGo без ключа) + trafilatura (извлечение текста страниц)
- (опционально) sqlite-vec или chromadb — векторный поиск
- (опционально) SearXNG — локальный приватный поисковик

## 3. Структура проекта

```
tg_assistant/
  run.py                     # точка входа: поднимает Telethon + FastAPI вместе
  config.example.yaml        # пример настроек (копируется в config.yaml)
  .env.example               # секреты (api_id/api_hash/пароль панели)
  requirements.txt
  nersiti_tg/
    config.py                # загрузка .env + yaml -> объект Settings
    logging_setup.py         # единая настройка логов
    telegram/
      client.py              # создание/авторизация Telethon-клиента
      handlers.py            # обработчики событий -> архив + автоответ
      sender.py              # отправка, "печатает...", черновики
    storage/
      db.py                  # схема SQLite, миграции, connection
      models.py              # dataclass-модели строк
      media.py               # скачивание и хранение файлов на диск
      search.py              # поиск: FTS5 (+ опц. векторный)
    ai/
      ollama_client.py       # клиент к Ollama (generate/chat/embeddings, tools)
      persona.py             # редактируемая персона + память
      reply.py               # промпт из истории + цикл tool-calling -> ответ
      tools.py               # доступ в интернет: web_search / web_fetch
      embeddings.py          # опц. семантическая память (RAG)
    autoreply/
      rules.py               # per-chat настройки и режимы (модель данных)
      engine.py              # ядро: решает, отвечать ли и как
      queue.py               # очередь черновиков на подтверждение
    dashboard/
      app.py                 # FastAPI: тумблеры, режимы, очередь, поиск
      templates/             # HTML (Jinja2)
      static/                # css/js
  scripts/
    setup_model.ps1|.sh      # установка готовой модели (ollama pull)
  docs/
    PLAN.md                  # этот файл
<storage.data_dir>/  (ОТДЕЛЬНЫЙ диск ПК, напр. D:/nersiti_data; НЕ в репозитории)
  archive.db                 # база
  media/<chat_id>/<yyyy-mm>/ # файлы
  session.session           # сессия Telethon
  persona.md                # редактируемая персона/память
  app.log                    # логи
```
Все пути формируются от `storage.data_dir` (config). Директории создаются
при первом запуске. На этом диске должно быть достаточно места под медиа.

## 4. Конфигурация

### .env (секреты, НЕ коммитить)
```
TG_API_ID=...            # с https://my.telegram.org
TG_API_HASH=...
DASHBOARD_PASSWORD=...    # пароль на вход в веб-панель
DASHBOARD_HOST=127.0.0.1
DASHBOARD_PORT=8765
```

### config.yaml (поведение)
```yaml
storage:
  data_dir: "D:/nersiti_data"   # ОТДЕЛЬНЫЙ диск. Linux: "/mnt/disk2/nersiti_data"

ai:
  provider: ollama
  base_url: "http://127.0.0.1:11434"
  model: "qwen2.5:7b-instruct"  # разговорная + умеет tools (function calling)
  embed_model: "bge-m3"
  temperature: 0.7
  max_tokens: 512
  context_messages: 20        # сколько последних сообщений давать в контекст
  use_tools: true             # разрешить модели ходить в интернет (см. web)

web:                          # доступ в интернет для модели (§7a)
  enabled: true
  search_provider: "duckduckgo"   # duckduckgo | searxng | tavily
  searxng_url: "http://127.0.0.1:8080"
  tavily_api_key: ""
  max_results: 5
  fetch_timeout_sec: 15

archive:
  save_media: true
  save_deleted: true          # ловить удаления и помечать is_deleted
  save_edits: true            # версионировать правки

autoreply:
  default_mode: "off"         # off | draft | auto
  default_auto_submode: "generate"   # preset | generate | dialogue
  default_preset_text: "Привет! Отвечу чуть позже."
  min_delay_sec: 3            # человекоподобная задержка перед ответом
  max_delay_sec: 12
  typing_simulation: true
  # per-chat переопределения хранятся в БД (таблица chat_settings), не тут
```

## 5. Модель данных (storage/db.py, storage/models.py)

Таблицы SQLite:

`chats`
- chat_id INTEGER PK
- type TEXT           -- user|group|channel
- title TEXT
- username TEXT
- last_seen_at INTEGER

`messages`
- id INTEGER PK AUTOINCREMENT
- tg_message_id INTEGER
- chat_id INTEGER
- sender_id INTEGER
- sender_name TEXT
- text TEXT
- date INTEGER               -- unix time
- reply_to INTEGER           -- tg_message_id, на который отвечают
- is_outgoing INTEGER        -- 0/1
- is_deleted INTEGER DEFAULT 0
- edited_at INTEGER
- media_id INTEGER           -- FK на media.id или NULL
- raw_json TEXT              -- сырой объект события (на всякий)
- UNIQUE(chat_id, tg_message_id, edited_at)  -- версии правок отдельными строками

`messages_fts` (FTS5, external content = messages, поля: text, sender_name)

`media`
- id INTEGER PK
- chat_id INTEGER
- tg_message_id INTEGER
- kind TEXT                  -- photo|video|voice|document|sticker|...
- file_path TEXT             -- путь на диске в data/media/...
- mime TEXT
- size INTEGER
- downloaded INTEGER DEFAULT 0

`chat_settings` (per-chat автоответ)
- chat_id INTEGER PK
- mode TEXT                  -- off|draft|auto
- auto_submode TEXT          -- preset|generate|dialogue
- preset_text TEXT
- enabled INTEGER            -- быстрый тумблер вкл/выкл

`drafts` (очередь черновиков)
- id INTEGER PK
- chat_id INTEGER
- reply_to INTEGER
- text TEXT
- status TEXT                -- pending|sent|rejected|edited
- created_at INTEGER

db.py экспортирует: `init_db(path)`, `get_conn()`, `upsert_chat(...)`,
`insert_message(...)`, `mark_deleted(chat_id, tg_message_id)`,
`get_chat_settings(chat_id)`, `set_chat_settings(...)`, CRUD для drafts.

## 6. Telegram-слой

### telegram/client.py
- `build_client(settings) -> TelegramClient` — создаёт Telethon-клиент
  с session-файлом `data/session`. Первый запуск: интерактивный ввод
  номера/кода/2FA в консоли. Дальше — по сессии.

### telegram/handlers.py
Регистрирует хэндлеры Telethon и связывает их с архивом и автоответом:
- `on_new_message(event)`:
  1) `upsert_chat`; 2) если есть медиа — `media.download_and_store`;
  3) `insert_message`; 4) обновить FTS;
  5) если `event` входящее (не свой) — передать в `autoreply.engine.handle`.
- `on_message_edited(event)` — если `archive.save_edits`, добавить новую
  версию строки (edited_at != NULL).
- `on_message_deleted(event)` — если `archive.save_deleted`, `mark_deleted`.
- (опц.) стартовый бэкофилл истории: пройти по диалогам и втянуть
  последние N сообщений на первый запуск (функция `backfill(limit)`).

### telegram/sender.py
- `async send_reply(client, chat_id, text, reply_to=None, simulate_typing=True)`
  — при `simulate_typing` показать «печатает…», выждать задержку
  (autoreply.min/max_delay_sec), отправить.
- `async send_draft_now(draft_id)` — берёт черновик из БД и отправляет.

## 7. AI-слой (локальный Ollama + доступ в интернет)

### ai/ollama_client.py
Тонкий httpx-клиент к локальному Ollama:
- `async generate(prompt, system=None, **opts) -> str` (POST /api/generate)
- `async chat(messages: list[dict]) -> str` (POST /api/chat)
- `async embed(text) -> list[float]` (POST /api/embeddings)
- graceful-ошибки, если Ollama не запущен (понятное сообщение в лог/панель).

### ai/persona.py
- Читает/пишет `data/persona.md` — текст с описанием стиля, фактов о
  пользователе, «правил ответа». Это и есть редактируемая «личность».
- `get_persona() -> str`, `update_persona(text)`, `append_memory(note)`.
- Персону подставляем в system-prompt при каждой генерации.

### ai/reply.py
- `async make_reply(chat_id, incoming_text) -> str`:
  1) взять из БД последние `ai.context_messages` сообщений чата;
  2) (опц.) через embeddings.py достать релевантные старые фрагменты (RAG);
  3) собрать messages для `chat`: system = персона + инструкция режима,
     далее история, далее новое сообщение;
  4) ЕСЛИ `ai.use_tools` и `web.enabled` → запустить ЦИКЛ TOOL-CALLING (§7a);
     иначе обычный вызов ollama_client.chat;
  5) вернуть финальный текст.
- Функция чистая относительно отправки: только генерирует строку.

## 7a. Доступ в интернет (ai/tools.py + цикл в reply.py)

Смысл: локальная модель «умная в общении» И может достать свежую инфу из
сети, когда это нужно (новости, факты, ссылки). Веса — локальные; наружу
идут только веб-запросы, инициированные моделью через инструменты.

### ai/tools.py
- `async web_search(query, max_results) -> list[{title,url,snippet}]`
  провайдер из `web.search_provider`:
    - `duckduckgo` — библиотека ddgs, без ключа (дефолт);
    - `searxng` — GET на `web.searxng_url` (локальный, приватный);
    - `tavily` — API с ключом `web.tavily_api_key`.
- `async web_fetch(url, timeout) -> str` — httpx GET → trafilatura.extract
  → основной текст (обрезать до разумного лимита символов).
- `TOOLS_SPEC` — описания инструментов в формате Ollama `tools`
  (name, description, parameters JSON-schema).
- `async run_tool_call(name, arguments) -> str` — диспетчер имя→функция,
  результат сериализуется в строку для возврата модели.

### Цикл tool-calling (в reply.py)
1. Вызов `ollama_client.chat(messages, tools=TOOLS_SPEC)`.
2. Если ответ содержит `tool_calls` → для каждого выполнить
   `run_tool_call(...)`, добавить результат как message role="tool",
   снова вызвать chat. Повторять до финального ответа без tool_calls.
3. Ограничить число итераций (напр. 3), чтобы не зациклиться.
4. Если `web.enabled=false` — tools не передаём, модель работает офлайн.

Безопасность/приватность: web_fetch с таймаутом, лимитом размера и
белым/чёрным списком доменов при желании; поиск можно направить в
локальный SearXNG, чтобы запросы не уходили в сторонние сервисы.

### ai/embeddings.py (опционально, включается флагом)
- Индексирует сообщения (эмбеддинги в отдельной таблице/векторном хранилище),
  `search_semantic(chat_id, query, k) -> list[str]`. Если выключено — no-op.

## 8. Автоответ (ядро логики)

### autoreply/rules.py
Модель настроек и режимов (dataclass + enum):
- Mode: OFF / DRAFT / AUTO
- AutoSubmode: PRESET / GENERATE / DIALOGUE
Функции доступа к `chat_settings` (обёртки над db.py).

### autoreply/engine.py — главный сценарий (ТОЧНО по требованию пользователя)
`async handle(client, event, incoming_text, chat_id)`:
1. `s = get_chat_settings(chat_id)` (или дефолты из config).
2. Если `s.mode == OFF` или `s.enabled == 0` → ничего не делать.
3. Если `s.mode == DRAFT` (кнопочный режим):
   - сгенерировать текст:
       - submode PRESET → взять preset_text;
       - иначе → `ai.reply.make_reply(...)`;
   - положить в `drafts` со статусом `pending`;
   - НИЧЕГО не отправлять. Пользователь увидит черновик в веб-панели,
     где кнопки «Отправить / Изменить / Отклонить».
4. Если `s.mode == AUTO` (тумблер включён, отвечает сама):
   - PRESET     → отправить preset_text;
   - GENERATE   → сгенерировать ответ и отправить;
   - DIALOGUE   → как GENERATE, но с полным контекстом истории
                  (context_messages по максимуму) и памятью — «ведёт диалог»;
   - отправка через sender.send_reply с задержкой и «печатает…».
Важно: DRAFT — всегда с ручным подтверждением (кнопка). AUTO — без.
Это и есть: тумблер (auto) + кнопка (draft), три под-режима авто.

### autoreply/queue.py
- CRUD черновиков поверх db.py:
  `list_pending()`, `approve(draft_id, edited_text=None)`, `reject(draft_id)`.
- `approve` → sender.send_draft_now + пометить `sent`.

## 9. Модель: готовая, без обучения

Обучение (в т.ч. LoRA) НЕ делаем — по решению пользователя. Используем
ГОТОВУЮ модель из реестра Ollama:
- основная: `qwen2.5:7b-instruct` (разговорная, русский, tools);
- эмбеддинги: `bge-m3`;
- «без ограничений» (по желанию): `dolphin-mistral:7b` — поменять
  `ai.model` в config и раскомментировать pull в setup_model-скрипте.
Установка — `scripts/setup_model.ps1` (Windows) или `.sh` (Linux):
делает `ollama pull ...`. Модель качается на ПК пользователя, не в репозиторий.

Адаптация под пользователя — без дообучения, только «мягко»:
- **Память/персона** (`data/persona.md`) — ассистент через
  `persona.append_memory` дописывает факты и стиль; они идут в system-prompt.
- **RAG по архиву** (опц.) — подтягивает релевантные прошлые сообщения.
Веса модели не меняются; это просто контекст в промпте.

## 10. Веб-панель (dashboard/app.py)

FastAPI на 127.0.0.1, простая авторизация по DASHBOARD_PASSWORD (cookie-сессия).
Страницы/эндпоинты:
- `GET /` — список чатов + для каждого: тумблер enabled, селект mode
  (off/draft/auto), при auto — селект submode (preset/generate/dialogue),
  поле preset_text.
- `POST /chat/{id}/settings` — сохранить настройки чата.
- `GET /drafts` — очередь черновиков (pending): текст, кнопки
  «Отправить», «Изменить+Отправить», «Отклонить».
- `POST /drafts/{id}/approve`, `/reject`.
- `GET /search?q=...` — полнотекстовый поиск по архиву (FTS5),
  выдача с чатом/датой/отправителем и ссылкой на медиа, если есть.
- `GET /chat/{id}/history` — просмотр истории чата из архива.
- `POST /persona` — редактирование persona.md прямо из панели.
UI минималистичный (Jinja2 + немного CSS), без внешних CDN.

## 11. Точка входа (run.py)

- Загрузить config + .env.
- init_db, создать папки data/.
- Поднять Telethon-клиент (авторизация при первом запуске).
- Зарегистрировать хэндлеры.
- Запустить FastAPI (uvicorn) и Telethon в одном asyncio-loop
  (например, uvicorn programmatically + client.run_until_disconnected
  через asyncio.gather).
- Корректное завершение по Ctrl+C.

## 12. Порядок реализации (для исполнителя)

1. config.py, logging_setup.py, requirements.txt, .env/.yaml примеры.
2. storage/ (db, models, media, search) + тесты вставки/поиска.
3. telegram/ (client, handlers на архив — БЕЗ автоответа).
   Проверить: сообщения и файлы реально пишутся в data/.
4. ai/ (ollama_client, persona, reply). Проверить генерацию на Ollama.
5. autoreply/ (rules, engine, queue) — сначала DRAFT, потом AUTO.
6. dashboard/ (тумблеры, очередь, поиск, персона).
7. run.py — всё вместе.
8. Готовая модель ставится скриптом scripts/setup_model.* (обучения нет).

## 13. Безопасность и правила

- Всё локально, база и медиа не покидают машину.
- Панель только на 127.0.0.1 + пароль.
- Автоматизация userbot — серая зона правил Telegram; полный AUTO
  повышает риск ограничений аккаунта. Дефолт — DRAFT. Пользователь
  включает AUTO осознанно, по конкретным чатам.
- Секреты только в .env, .env в .gitignore.
