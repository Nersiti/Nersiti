# Установка готовой локальной модели для Nersiti TG Assistant (Windows, PowerShell)
# Обучать ничего не нужно — берём готовую модель из реестра Ollama.
# Запусти ОДИН РАЗ на своём ПК: правый клик -> "Запустить с помощью PowerShell",
# или в терминале:  powershell -ExecutionPolicy Bypass -File setup_model.ps1

Write-Host "1) Проверяю Ollama..." -ForegroundColor Cyan
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host "Ollama не найдена. Установи её с https://ollama.com/download и запусти скрипт снова." -ForegroundColor Yellow
    exit 1
}

Write-Host "2) Скачиваю разговорную модель с поддержкой инструментов..." -ForegroundColor Cyan
ollama pull qwen2.5:7b-instruct

Write-Host "3) Скачиваю модель эмбеддингов (для поиска по архиву)..." -ForegroundColor Cyan
ollama pull bge-m3

# --- ВАРИАНТ "БЕЗ ОГРАНИЧЕНИЙ" (по желанию) ---
# Раскомментируй строку ниже и укажи эту модель в config.yaml (ai.model),
# если нужна uncensored-модель. Инструменты у dolphin работают хуже, русский слабее.
# ollama pull dolphin-mistral:7b

Write-Host "Готово. В config.yaml ai.model = qwen2.5:7b-instruct" -ForegroundColor Green
Write-Host "Проверка: " -NoNewline; ollama list
