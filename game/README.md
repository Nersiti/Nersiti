# Битва за Мир: Telegram Mini App

Полный план и правила игры лежат в [`../PLAN.md`](../PLAN.md).

## Состав
- `backend/`: FastAPI (API для Mini App) + aiogram (бот через webhook) + воркер фоновых задач.
- `frontend/`: мини-приложение на React + Vite.
- `deploy/Caddyfile`: HTTPS и маршрутизация (`/api`, `/tg` уходят на backend, остальное раздаётся как статика).
- `docker-compose.yml`: postgres, redis, api, worker, caddy.

## Запуск на VPS

1. **Этап 0 (один раз, вручную):**
   - В [@BotFather](https://t.me/BotFather): `/newbot`, сохранить токен.
   - `Bot Settings → Configure Mini App → Enable Mini App`, URL: `https://<твой домен>/`.
   - A-запись домена (или поддомена, например `game.example.com`) направить на IP VPS.
   - На VPS установить Docker: `curl -fsSL https://get.docker.com | sh`, открыть порты 80 и 443.
2. Скопировать папку `game/` на VPS (или `git clone` репозитория).
3. `cp .env.example .env` и заполнить `.env` (токен, username бота, домен, пароли, свой Telegram ID в `ADMIN_IDS`).
4. Запустить:
   ```bash
   docker compose up -d --build
   docker compose run --rm api python -m app.bot.set_webhook
   ```
5. Сгенерировать карту мира (один раз, ~1–3 минуты; скачает ~190 МБ русских названий с GeoNames):
   ```bash
   docker compose run --rm api python -m app.scripts.build_world
   ```
   Получится ≈21,6 тыс. городов и ≈215 тыс. секторов. Районы крупных городов (например, «Марьино») сливаются с городом, спутники из другого региона (Химки) остаются отдельными городами. Если GeoNames недоступен, русские названия подбираются эвристикой (`--ru-names heuristic`), и в них бывают неточности.
6. Написать боту `/start` и нажать «Играть».

Проверка: `https://<домен>/api/health` должен отвечать `{"ok": true}`.
Логи: `docker compose logs -f api worker`.

## Бэкапы

```bash
chmod +x deploy/*.sh
./deploy/backup.sh          # дамп в backups/, хранятся последние 7
./deploy/restore_check.sh   # проверка: восстановить последний дамп во временную БД
```
Автоматически каждый день (на VPS: `crontab -e`):
```
15 4 * * * cd /opt/game && ./deploy/backup.sh >> backups/backup.log 2>&1
```
Полное восстановление (если сервер умер): поднять стек на новом VPS, затем
`docker compose exec -T postgres pg_restore -U game -d game --clean --if-exists < backups/<файл>.dump`.
Папку `backups/` стоит периодически копировать на хостинг или к себе (например, `rsync`).

## Команды администратора (в личке с ботом, твой ID в `ADMIN_IDS`)
- `/admin` — список команд, `/stats` — игроки, DAU/WAU/MAU, выручка Stars, реклама.
- `/suspects`, `/ban <id>`, `/unban <id>`, `/ban_clan <id>` — модерация.
- `/broadcast <текст>` — рассылка всем (с подтверждением).
- `/task_add @канал <награда> <кол-во|0> <название>`, `/task_link <url> <награда> <название>`, `/tasks`, `/task_off <id>`.
- Заявки рекламодателей из `/promote` приходят сюда с кнопками «Одобрить / Отклонить и вернуть звёзды».
- `/combo_set today market walls barracks` — комбо дня; `/season_end` — завершить сезон вручную.
- `/gifts`, `/gift <user_id> <gift_id>` — подарки Telegram победителям (оплачиваются звёздами бота).
- `/refund <charge_id>` — вернуть звёзды за покупку.

## Реклама Adsgram
1. Зарегистрируйся на adsgram.ai, создай блок типа Reward для своего бота, получи `blockId`.
2. В настройках блока укажи Reward URL: `https://<домен>/api/ads/callback?userid=[userId]&secret=<ADS_CALLBACK_SECRET>`.
3. Впиши `ADSGRAM_BLOCK_ID` и `ADS_CALLBACK_SECRET` в `.env` и перезапусти `docker compose up -d`.

## Чек-лист перед запуском
1. `.env`: `ENV=prod`, `DEV_MODE=false`, сильный `POSTGRES_PASSWORD`, случайный `WEBHOOK_SECRET`, свой ID в `ADMIN_IDS`, `WEB_CONCURRENCY` по числу vCPU.
2. `docker compose up -d --build`, затем `set_webhook` и `build_world` (см. выше).
3. Открыть бота, пройти онбординг, захватить сектор, купить тестовый товар за 1 ⭐ (`test_star` виден только админам) и проверить, что пришло сообщение об оплате.
4. `/stats` в боте показывает цифры; `/admin` — список команд.
5. Настроить cron для `deploy/backup.sh` и один раз прогнать `deploy/restore_check.sh`.
6. В @BotFather: описание, аватар, `/setprivacy` не нужен; включить Main Mini App, чтобы игра была в поиске Telegram; настроить партнёрскую программу Stars (Affiliate Program) — 20–30% комиссии.
7. (По желанию) Adsgram — см. раздел выше.

## Нагрузочный тест
Сценарий в `loadtest/locustfile.py` (игроки тапают, опрашивают карту, атакуют, покупают улучшения). Запускать **только на тестовой копии** с `DEV_MODE=true`:
```bash
pip install locust h3
locust -f loadtest/locustfile.py --host http://localhost:8000 --headless -u 1000 -r 50 -t 5m
```
Результат на 4 ядрах (сервер, PostgreSQL, Redis и сам генератор нагрузки на одной машине, 3 воркера API):
1000 виртуальных игроков → ~500 запросов/с, 0 ошибок, медиана 24 мс, p95 ≈ 450 мс.
Виртуальный игрок шлёт запрос раз в 1–3 секунды, это в ~10 раз чаще настоящего клиента
(тапы уходят пачкой раз в 10 с, карта обновляется раз в 15 с), так что это соответствует примерно 2–3 тысячам
одновременно играющих людей. При 300 виртуальных игроках: ~165 запросов/с, p95 ≈ 150 мс.
Узкое место — CPU воркеров API: при росте добавляй `WEB_CONCURRENCY`/ядра, затем выноси PostgreSQL на отдельный сервер.

## Локальная разработка

Нужны Python 3.11+, Node 22, PostgreSQL 16 и Redis 7.

```bash
# backend
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
export ENV=dev DEV_MODE=true BOT_TOKEN=123:abc WEBHOOK_SECRET=dev \
       DATABASE_URL=postgresql+asyncpg://game:game@localhost:5432/game \
       REDIS_URL=redis://localhost:6379/0
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# frontend (в другом терминале)
cd frontend && npm install && npm run dev
```

В режиме `DEV_MODE=true` API принимает заголовок `Authorization: dev <user_id>`: можно открыть игру в обычном браузере и играть за разных пользователей. Чтобы переключиться на другого пользователя, выполни в консоли браузера `localStorage.devUserId = 2`. **В проде `DEV_MODE` всегда `false`**: при `ENV=prod` приложение с `DEV_MODE=true` не запустится.

### Тесты
```bash
cd backend
createdb game_test   # один раз
pytest               # использует TEST_DATABASE_URL / TEST_REDIS_URL (по умолчанию localhost)
ruff check .
cd ../frontend && npm run build
```
