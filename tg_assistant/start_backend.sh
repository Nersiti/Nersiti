#!/usr/bin/env bash
# Запуск бэкенда-мозга Nersiti «под ключ»: venv, зависимости, тесты, сервер.
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then python3 -m venv .venv; fi
. .venv/bin/activate
pip -q install --upgrade pip >/dev/null
pip -q install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Создан .env из примера. Впиши SYNC_TOKEN (и TG_* при необходимости)."
fi
if [ ! -f config.yaml ]; then
  cp config.example.yaml config.yaml
  echo "Создан config.yaml. Проверь storage.data_dir (диск для архива)."
fi

echo "== тесты =="
python -m pytest -q tests/ || { echo "Тесты упали"; exit 1; }

echo "== запуск сервера (Ctrl+C для остановки) =="
python run.py
