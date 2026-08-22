#!/usr/bin/env bash
# Автосборка APK мода Nersiti на базе открытого форка Telegram (exteraGram).
# Запускать на машине с интернетом и ~15 ГБ свободного места.
#
# ОБЯЗАТЕЛЬНО задать свои секреты (с https://my.telegram.org):
#   export TG_API_ID=123456
#   export TG_API_HASH=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
#   export BACKEND_URL="http://192.168.1.10:8765"   # адрес ПК-мозга
#   export SYNC_TOKEN="совпадает с бэкендом"
#
# Затем:  bash build_apk.sh
set -e

: "${TG_API_ID:?Задай TG_API_ID (my.telegram.org)}"
: "${TG_API_HASH:?Задай TG_API_HASH (my.telegram.org)}"
: "${BACKEND_URL:=http://192.168.1.10:8765}"
: "${SYNC_TOKEN:=change_me_long_random}"

FORK_URL="${FORK_URL:-https://github.com/exteraSquad/exteraGram.git}"
WORK="${WORK:-$PWD/_apk_build}"
HERE="$(cd "$(dirname "$0")" && pwd)"

echo "==> 1/5 Проверка Android SDK/NDK"
if [ -z "$ANDROID_HOME" ] && [ -z "$ANDROID_SDK_ROOT" ]; then
  echo "ВНИМАНИЕ: Android SDK не найден. Установи Android Studio или cmdline-tools,"
  echo "затем: sdkmanager 'platform-tools' 'platforms;android-34' 'build-tools;34.0.0' 'ndk;27.0.12077973'"
  echo "и задай ANDROID_HOME. Скрипт продолжит, gradle сам подскажет чего не хватает."
fi

echo "==> 2/5 Клонирование форка: $FORK_URL"
mkdir -p "$WORK"
if [ ! -d "$WORK/src/.git" ]; then
  git clone --depth 1 "$FORK_URL" "$WORK/src"
fi

echo "==> 3/5 Встраивание моста Nersiti"
# путь к пакету может отличаться в форке; типовой — TMessagesProj/src/main/java/org/telegram
DEST="$WORK/src/TMessagesProj/src/main/java/org/telegram/nersiti"
mkdir -p "$DEST"
cp "$HERE/nersiti/"*.java "$DEST/"

echo "==> 4/5 Подстановка секретов (api_id/api_hash/бэкенд)"
# api_id/api_hash: обычно в BuildVars.java (APP_ID / APP_HASH) — правим при наличии.
BV=$(grep -rl "APP_ID" "$WORK/src" --include=BuildVars.java | head -1 || true)
if [ -n "$BV" ]; then
  sed -i "s/public static int APP_ID = .*/public static int APP_ID = ${TG_API_ID};/" "$BV" || true
  sed -i "s/public static String APP_HASH = .*/public static String APP_HASH = \"${TG_API_HASH}\";/" "$BV" || true
  echo "    обновлён $BV"
else
  echo "    BuildVars.java не найден — впиши APP_ID/APP_HASH вручную (см. BUILD_APK.md)."
fi
# наши настройки моста
NC="$DEST/NersitiConfig.java"
sed -i "s#BACKEND_URL = \".*\"#BACKEND_URL = \"${BACKEND_URL}\"#" "$NC"
sed -i "s#SYNC_TOKEN = \".*\"#SYNC_TOKEN = \"${SYNC_TOKEN}\"#" "$NC"

echo "==> 5/5 Сборка APK (gradle)"
cd "$WORK/src"
if [ -x ./gradlew ]; then
  ./gradlew assembleRelease || {
    echo "Сборка упала. Частые причины: не установлен NDK нужной версии,"
    echo "нет keystore для подписи, отсутствует google-services.json."
    echo "См. docs/BUILD_APK.md."
    exit 1
  }
else
  echo "gradlew не найден в форке."; exit 1
fi

echo "Готово. Ищи APK в TMessagesProj/build/outputs/apk/"
