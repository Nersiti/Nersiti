#!/usr/bin/env bash
# Установка и запуск бота на сервере (Ubuntu/Debian) через Docker.
# Использование: bash deploy/setup_server.sh
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v docker >/dev/null 2>&1; then
  echo ">>> Устанавливаю Docker..."
  curl -fsSL https://get.docker.com | sh
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo ">>> Создан .env. Впиши BOT_TOKEN и ADMIN_IDS (nano .env) и запусти скрипт ещё раз."
  exit 1
fi

if grep -q "your-token-here" .env; then
  echo ">>> В .env остался токен-пример. Впиши настоящий BOT_TOKEN от @BotFather."
  exit 1
fi

mkdir -p data backups
docker compose up -d --build
sleep 5
docker compose logs --tail=30 bot
echo
echo ">>> Готово. Логи: docker compose logs -f bot"
echo ">>> Обновление: git pull && docker compose up -d --build"
echo ">>> Бэкап базы по cron: 0 4 * * * cd $(pwd) && bash deploy/backup.sh"
