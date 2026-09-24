# ============================================================
#  Настройка ПК с видеокартой NVIDIA (RTX 5060 и др.) как «нейросервера» для бота.
#
#  Запуск (PowerShell от имени администратора):
#    Set-ExecutionPolicy -Scope Process Bypass
#    .\scripts\windows\setup_gpu_pc.ps1
#
#  Что делает:
#    1) ставит Ollama (текстовая нейросеть), 7-Zip и Tailscale (защищённая сеть ПК <-> сервер)
#    2) скачивает ComfyUI portable (картинки, поддерживает RTX 50xx) и модель SDXL (~7 ГБ)
#    3) скачивает языковую модель для Ollama
#    4) открывает порты 8188 и 11434 только для сети Tailscale
# ============================================================
param(
    [string]$Dir = "C:\AI",
    [string]$LlmModel = "qwen2.5:7b",
    [switch]$SkipSdxl,
    [switch]$SkipLlm
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Step($text) { Write-Host "`n=== $text ===" -ForegroundColor Cyan }

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)

Step "1/5 Установка Ollama, 7-Zip, Tailscale"
foreach ($id in @("Ollama.Ollama", "7zip.7zip", "Tailscale.Tailscale")) {
    winget install -e --id $id --accept-source-agreements --accept-package-agreements --silent
}

Step "2/5 Настройка Ollama для доступа по сети"
[Environment]::SetEnvironmentVariable("OLLAMA_HOST", "0.0.0.0:11434", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_KEEP_ALIVE", "10m", "User")
Write-Host "Готово. После установки перезапусти Ollama (значок в трее -> Quit и запусти снова)."

Step "3/5 ComfyUI portable"
New-Item -ItemType Directory -Force -Path $Dir | Out-Null
$comfy = Join-Path $Dir "ComfyUI_windows_portable"
if (-not (Test-Path $comfy)) {
    $archive = Join-Path $Dir "ComfyUI_windows_portable_nvidia.7z"
    curl.exe -L --fail -o $archive "https://github.com/comfyanonymous/ComfyUI/releases/latest/download/ComfyUI_windows_portable_nvidia.7z"
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось скачать ComfyUI. Скачай портативную версию для NVIDIA вручную: https://github.com/comfyanonymous/ComfyUI/releases и распакуй в $Dir"
    }
    & "C:\Program Files\7-Zip\7z.exe" x $archive "-o$Dir" -y | Out-Null
    Remove-Item $archive
} else {
    Write-Host "ComfyUI уже установлен: $comfy"
}
Copy-Item -Force (Join-Path $PSScriptRoot "start_comfyui.bat") (Join-Path $Dir "start_comfyui.bat")

Step "4/5 Модель для картинок (SDXL 1.0, коммерческое использование разрешено)"
$ckpt = Join-Path $comfy "ComfyUI\models\checkpoints\sd_xl_base_1.0.safetensors"
if ($SkipSdxl) {
    Write-Host "Пропущено (-SkipSdxl)."
} elseif (Test-Path $ckpt) {
    Write-Host "Модель уже скачана."
} else {
    curl.exe -L --fail -o $ckpt "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors"
    if ($LASTEXITCODE -ne 0) { Write-Warning "Модель не скачалась — скачай вручную в $ckpt" }
}

Step "5/5 Языковая модель и брандмауэр"
$ollama = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
if ($SkipLlm) {
    Write-Host "Пропущено (-SkipLlm)."
} elseif (Test-Path $ollama) {
    Start-Process -FilePath $ollama -ArgumentList "serve" -WindowStyle Hidden -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 5
    & $ollama pull $LlmModel
} else {
    Write-Warning "Ollama не найдена. Позже выполни: ollama pull $LlmModel"
}

if ($isAdmin) {
    foreach ($port in 8188, 11434) {
        $name = "AI bot port $port (Tailscale only)"
        if (-not (Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue)) {
            New-NetFirewallRule -DisplayName $name -Direction Inbound -Protocol TCP -LocalPort $port `
                -RemoteAddress 100.64.0.0/10 -Action Allow | Out-Null
        }
    }
    Write-Host "Порты 8188 и 11434 открыты только для сети Tailscale."
} else {
    Write-Warning "Запусти скрипт от администратора, чтобы открыть порты в брандмауэре."
}

Write-Host "`n============================================================" -ForegroundColor Green
Write-Host "Готово! Дальше:" -ForegroundColor Green
Write-Host " 1. Открой Tailscale и войди в аккаунт (тот же, что на сервере)."
Write-Host " 2. Запусти $Dir\start_comfyui.bat (окно не закрывай)."
Write-Host " 3. Перезапусти Ollama из трея."
Write-Host " 4. Узнай IP этого ПК в Tailscale:  & 'C:\Program Files\Tailscale\tailscale.exe' ip -4"
Write-Host " 5. На сервере в .env пропиши:"
Write-Host "      LLM_BASE_URL=http://<IP>:11434/v1"
Write-Host "      IMAGE_API_URL=http://<IP>:8188"
Write-Host "============================================================" -ForegroundColor Green
