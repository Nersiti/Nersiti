# Сборка APK мода Nersiti — пошагово

Честно: собрать функциональный APK можно только с ТВОИМИ `api_id`/`api_hash`
(их генерируешь только ты, они привязаны к твоему номеру). Без них клиент
не подключится к Telegram. Ниже — весь процесс; автоматизирует его
`android_mod/build_apk.sh`.

## Что понадобится
- ПК с интернетом и ~15 ГБ свободного места (лучше Linux/WSL или macOS).
- JDK 17, Android Studio (или cmdline-tools) + SDK + NDK.
- Свои `api_id` и `api_hash`: https://my.telegram.org -> API development tools.
- Запущенный бэкенд-мозг (этот проект, `python run.py`) и его адрес в сети.

## Шаг 1. Установить инструменты
- Android Studio (проще всего) либо cmdline-tools:
  `sdkmanager "platform-tools" "platforms;android-34" "build-tools;34.0.0" "ndk;27.0.12077973"`
- Задать `ANDROID_HOME` на папку SDK.

## Шаг 2. Задать секреты и параметры
```
export TG_API_ID=123456
export TG_API_HASH=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
export BACKEND_URL="http://192.168.1.10:8765"   # адрес ПК с бэкендом
export SYNC_TOKEN="тот же, что в .env бэкенда (SYNC_TOKEN)"
```

## Шаг 3. Запустить автосборку
```
bash android_mod/build_apk.sh
```
Скрипт: клонирует форк (по умолчанию exteraGram), копирует пакет
`org.telegram.nersiti` (наш мост) в исходники, подставляет api_id/api_hash и
адрес бэкенда, запускает `gradlew assembleRelease`.

## Шаг 4. Точки интеграции в форк (правки ядра, ~5 мест)
Наш мост (`NersitiBridge`) готов; его нужно ВЫЗВАТЬ из кода форка:
1. `NersitiBridge.init(context)` — при старте приложения.
2. При получении/отправке сообщения -> `NersitiBridge.onMessage(...)`.
3. При получении исчезающего/one-time медиа -> `onDisappearingMedia(...)`
   (в форках exteraGram/Owlgram уже есть места, где снимается self-destruct —
   туда и вставляем сохранение).
4. При расшифровке секретного чата -> `onSecretMessage(...)`.
5. Удаление сообщения -> `onDeleted(...)`; кнопка «Архив чата»/панель
   черновика -> `requestReply(...)`.
Конкретные файлы зависят от версии форка (искать по классам обработки
сообщений и таймеров self-destruct).

## Шаг 5. Подпись и установка
- Для release нужен keystore:
  `keytool -genkey -v -keystore nersiti.keystore -alias nersiti -keyalg RSA -keysize 2048 -validity 10000`
  и прописать его в `signingConfigs` gradle форка (или собрать debug-APK для теста).
- Перекинуть APK на телефон, разрешить установку из неизвестных источников,
  установить. Войти под своим аккаунтом.

## Частые проблемы
- Сборка падает без NDK нужной версии — доустановить через sdkmanager.
- Нужен `google-services.json` (пуши) — можно отключить в gradle для личной сборки.
- `APP_ID/APP_HASH` не подставились — вписать вручную в `BuildVars.java`.

## Обновления Telegram
Форк придётся периодически подтягивать (rebase наших правок поверх upstream) —
это плата за путь «мод». Наш пакет `org.telegram.nersiti` при этом не меняется,
меняются только 5 точек вызова из шага 4.
