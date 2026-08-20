#!/usr/bin/env bash
# Установка готовой локальной модели для Nersiti TG Assistant (Linux/macOS).
# Обучать ничего не нужно — берём готовую модель из реестра Ollama.
set -e

echo "1) Проверяю Ollama..."
if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama не найдена. Установи: https://ollama.com/download , затем запусти снова."
  exit 1
fi

echo "2) Скачиваю разговорную модель с поддержкой инструментов..."
ollama pull qwen2.5:7b-instruct

echo "3) Скачиваю модель эмбеддингов (для поиска по архиву)..."
ollama pull bge-m3

# Вариант "без ограничений" (по желанию): раскомментируй и укажи в config.yaml.
# ollama pull dolphin-mistral:7b

echo "Готово. В config.yaml ai.model = qwen2.5:7b-instruct"
ollama list
