# android_mod — сторона телефона (мод Telegram)

Мост **Nersiti**, который встраивается в открытый форк Telegram (exteraGram
и т.п.) и связывает его с бэкендом-мозгом на ПК.

## Файлы
- `nersiti/NersitiConfig.java` — адрес бэкенда, токен, флаги (исчезающие/секретные).
- `nersiti/NersitiStore.java`  — локальный SQLite-архив на телефоне.
- `nersiti/NersitiSync.java`   — HTTP-клиент к бэкенду (/sync, /ai/reply, /health).
- `nersiti/NersitiBridge.java` — фасад: единственная точка вызова из форка.
- `build_apk.sh`               — автосборка APK (клон форка + встраивание + gradle).

## Как использовать
См. `../docs/BUILD_APK.md`. Кратко:
1. Задать `TG_API_ID`, `TG_API_HASH`, `BACKEND_URL`, `SYNC_TOKEN` в окружении.
2. `bash build_apk.sh`.
3. Вызвать `NersitiBridge` из 5 точек форка (список в BUILD_APK.md, шаг 4).

Мост максимально изолирован: при обновлении форка меняются только точки
вызова, сам пакет `org.telegram.nersiti` остаётся как есть.
