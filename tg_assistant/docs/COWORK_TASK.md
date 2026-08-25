# ЗАДАНИЕ для Claude Cowork: доделать и собрать Nersiti (бэкенд + мод Telegram APK)

Ты — Claude Cowork на ПК пользователя. Твоя задача: довести проект Nersiti до
рабочего состояния и собрать устанавливаемый APK мода Telegram, затем всё
запустить. Большая часть уже сделана и протестирована — тебе остаётся сборка
Android-части и связка end-to-end. Общайся с пользователем по-русски.

## Контекст (что уже готово)
- Репозиторий: `Nersiti/Nersiti`, ветка `claude/telegram-ai-integration-2s8p32`.
- Проект в папке `tg_assistant/`. Читай:
  - `docs/PLAN.md` — бэкенд-мозг (архитектура, схема, API).
  - `docs/PLAN_MOD_ANDROID.md` — клиент (мод Telegram, сохранение исчезающих медиа).
  - `docs/BUILD_APK.md` — сборка APK.
- **Бэкенд (Python) реализован и протестирован** (`pytest` зелёный):
  хранилище SQLite+FTS5 (поля исчезающих/секретных медиа), sync-API
  (`/sync/messages`, `/sync/media`, `/ai/reply`, `/health`), API панели,
  движок автоответа. Нейросеть (Ollama) подключается «в один провод».
- **Мост для мода** в `tg_assistant/android_mod/` (Java): `NersitiConfig`,
  `NersitiStore`, `NersitiSync`, `NersitiBridge` + `build_apk.sh`.

## ВХОДНЫЕ ДАННЫЕ ОТ ПОЛЬЗОВАТЕЛЯ (спроси, если не заданы!)
Без этого рабочий APK невозможен — их генерирует только пользователь:
1. `TG_API_ID` и `TG_API_HASH` — с https://my.telegram.org (API development tools).
2. IP ПК в локальной сети (адрес бэкенда для телефона), напр. `192.168.1.10`.
3. Придумать `SYNC_TOKEN` (общий секрет телефон↔ПК).
Если чего-то нет — ОСТАНОВИСЬ и попроси у пользователя, не выдумывай.

## Окружение
- Бэкенд и Ollama — нативно на Windows/Linux/macOS (Python 3.11+).
- **Сборка Android APK лучше всего в Linux / WSL2 (Ubuntu) / macOS.** Если ПК
  на Windows — используй WSL2. Нужны: JDK 17, Android SDK, NDK.

---

## ФАЗА 1. Запустить и проверить бэкенд-мозг
```
cd tg_assistant
bash start_backend.sh        # создаст venv, поставит зависимости, прогонит тесты, запустит сервер
```
- Проверка: `curl http://127.0.0.1:8765/health` -> `{"ok":true,...}`.
- Впиши в `.env` придуманный `SYNC_TOKEN`. Перезапусти при изменении.
DONE-критерий: `/health` отвечает, `pytest` зелёный.

## ФАЗА 2. Подключить нейросеть (Ollama)
```
# установить Ollama: https://ollama.com/download
bash scripts/setup_model.sh   # или setup_model.ps1 на Windows: тянет qwen2.5:7b-instruct и bge-m3
```
- Проверка генерации через бэкенд:
```
# создать чат-настройку auto/generate и запросить ответ
curl -s -X POST http://127.0.0.1:8765/ai/reply \
  -H "X-Sync-Token: <SYNC_TOKEN>" -H "Content-Type: application/json" \
  -d '{"chat_id": 1, "incoming_text": "привет, как дела?"}'
```
  Ожидаем `{"action":"none",...}` пока для чата не выставлен режим, ИЛИ
  осмысленный текст, если задать режим. Задать режим можно так:
```
curl -s -X POST http://127.0.0.1:8765/api/chat/1/settings \
  -H "Content-Type: application/json" \
  -d '{"mode":"auto","auto_submode":"generate","enabled":1}'
```
  Повторный `/ai/reply` должен вернуть `action":"send"` с текстом от модели.
DONE-критерий: `/ai/reply` возвращает сгенерированный текст при запущенном Ollama.

## ФАЗА 3. Собрать базовый форк «как есть» (проверка тулчейна)
Цель — убедиться, что APK вообще собирается и логинится, ДО наших правок.
```
# WSL2/Linux: установить JDK17, Android SDK+NDK (см. docs/BUILD_APK.md шаг 1)
export TG_API_ID=...  TG_API_HASH=...  BACKEND_URL="http://<IP_ПК>:8765"  SYNC_TOKEN="..."
cd tg_assistant/android_mod
FORK_URL="https://github.com/exteraSquad/exteraGram.git" BUILD_TYPE=debug bash build_apk.sh
```
- Если exteraGram неудобен/не собирается — допускается другой активный
  открытый форк (Nekogram X, Owlgram). Зафиксируй выбор в комментарии коммита.
- Скрипт клонирует форк, копирует наш пакет `org.telegram.nersiti`, подставляет
  api_id/api_hash и адрес бэкенда, собирает **debug-APK** (ставится без keystore).
DONE-критерий: получен `.apk`, ставится на телефон, логинится под аккаунтом.

## ФАЗА 4. Встроить мост Nersiti в форк (5 точек)
Наш код уже в исходниках форка (пакет `org.telegram.nersiti`). Нужно его ВЫЗВАТЬ.
Найди в форке места и вставь вызовы (детали — docs/BUILD_APK.md шаг 4):
1. Инициализация при старте приложения -> `NersitiBridge.init(context)`
   (класс Application/ApplicationLoader форка).
2. Приём/отправка сообщения (обработчик updates / MessagesController) ->
   `NersitiBridge.onMessage(...)`.
3. Исчезающее / one-time медиа (места, где форк уже работает с self-destruct
   таймером; в exteraGram/Owlgram это включаемая функция) ->
   `NersitiBridge.onDisappearingMedia(...)`.
4. Расшифровка секретного чата (SecretChatHelper) -> `NersitiBridge.onSecretMessage(...)`.
5. Удаление сообщения -> `NersitiBridge.onDeleted(...)`.
Плюс минимальный UI (можно этапом позже): иконка «Архив чата» в шапке чата и
панель черновика над полем ввода, дёргающая `NersitiBridge.requestReply(...)`.
Также допиши в `NersitiBridge.pushAsync(...)` реальную выгрузку: собери JSON и
вызови `NersitiSync.syncMessages(...)`, при успехе `store.markSynced(row)`.
Пересобери: `BUILD_TYPE=debug bash build_apk.sh`.
DONE-критерий: сообщения с телефона появляются в архиве на ПК (см. Фазу 5).

## ФАЗА 5. Проверка end-to-end
1. Телефон и ПК в одной сети; бэкенд запущен; в APK прописан `BACKEND_URL` и `SYNC_TOKEN`.
2. Напиши себе сообщение в Telegram -> проверь на ПК:
```
curl -s "http://127.0.0.1:8765/api/chats"
curl -s "http://127.0.0.1:8765/api/chat/<chat_id>/archive"
```
   Сообщение должно быть в архиве. Файлы — в `storage.data_dir/media/...`.
3. Пришли себе исчезающее фото/one-time -> оно должно сохраниться (флаг
   `was_disappearing=1` в архиве, файл на диске).
4. Черновик: включи для чата `mode=draft` -> входящее сообщение создаёт
   черновик (`/api/drafts`), в приложении он виден над полем ввода.
DONE-критерий: все 4 пункта проходят.

## ФИНАЛ (сразу запуск)
- Оставь бэкенд запущенным (`start_backend.sh`), Ollama запущен.
- Установи собранный APK на телефон, войди в аккаунт, проверь Фазу 5.
- Закоммить свои изменения в ветку `claude/telegram-ai-integration-2s8p32`
  (интеграционные правки форка держи отдельной папкой/патчем в `android_mod/`,
  не коммить весь форк в репозиторий — только наши файлы и патч-инструкции).
- Кратко отпишись пользователю: что собрано, где APK, что запущено, что осталось.

## ВАЖНО (честно и ответственно)
- api_id/api_hash — личные секреты пользователя, не логируй их и не коммить.
- Функция сохранения исчезающих/секретных медиа — для личного архива своих
  полученных сообщений; предупреди пользователя об ответственном использовании.
- Полный авто-режим повышает риск ограничений аккаунта Telegram; дефолт — draft.
- Если фаза не проходит — не имитируй успех, честно опиши, что застряло.
