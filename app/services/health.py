"""Neural network fuses and connection checks.

If the GPU PC is off or the LLM doesn't respond, it's wasteful to make every player wait for a timeout: after the first
failures, the fuse "opens", and for a while the game uses fallbacks (template creatures, cards without art).
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import httpx

from app.config import Settings
from app.services.images import ImageBackend, ImageRequest
from app.services.llm import LLMClient, LLMError, Messages


class Breaker:
    def __init__(self, threshold: int = 2, cooldown: float = 45.0) -> None:
        self.threshold = threshold
        self.cooldown = cooldown
        self._failures = 0
        self._open_until = 0.0

    @property
    def is_open(self) -> bool:
        return time.monotonic() < self._open_until

    def success(self) -> None:
        self._failures = 0
        self._open_until = 0.0

    def failure(self) -> None:
        self._failures += 1
        if self._failures >= self.threshold:
            self._open_until = time.monotonic() + self.cooldown


class GuardedLLM:
    """Wrapper around the LLM: while the fuse is open, fails instantly instead of waiting for a timeout."""

    def __init__(self, inner: LLMClient, breaker: Breaker | None = None) -> None:
        self.inner = inner
        self.breaker = breaker or Breaker()

    async def complete(
        self, messages: Messages, max_tokens: int | None = None, temperature: float | None = None
    ) -> str:
        if self.breaker.is_open:
            raise LLMError("LLM temporarily disabled after failures")
        try:
            result = await self.inner.complete(messages, max_tokens, temperature)
        except (Exception, asyncio.CancelledError):
            self.breaker.failure()
            raise
        self.breaker.success()
        return result

    async def close(self) -> None:
        await self.inner.close()


class GuardedImages:
    def __init__(self, inner: ImageBackend, breaker: Breaker | None = None) -> None:
        self.inner = inner
        self.breaker = breaker or Breaker(threshold=1, cooldown=60.0)

    async def generate(self, req: ImageRequest) -> bytes:
        if self.breaker.is_open:
            raise RuntimeError("image backend temporarily disabled after a failure")
        try:
            data = await self.inner.generate(req)
        except (Exception, asyncio.CancelledError):
            self.breaker.failure()
            raise
        self.breaker.success()
        return data

    async def close(self) -> None:
        await self.inner.close()


# ---------- проверка подключения ----------


async def _get_json(url: str, headers: dict[str, str] | None = None) -> Any:
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=5.0)) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def check_llm(settings: Settings) -> str:
    if settings.llm_backend == "mock":
        return "⚪ выключена (LLM_BACKEND=mock) — существа по шаблону"
    headers = {}
    if key := settings.llm_api_key.get_secret_value():
        headers["Authorization"] = f"Bearer {key}"
    try:
        data = await _get_json(settings.llm_base_url.rstrip("/") + "/models", headers)
    except Exception as e:  # noqa: BLE001
        return f"🔴 недоступна ({settings.llm_base_url}): {type(e).__name__}"
    models = [m.get("id", "") for m in (data.get("data") or [])] if isinstance(data, dict) else []
    if models and settings.llm_model not in models:
        sample = ", ".join(models[:5])
        return f"🟡 доступна, но модели «{settings.llm_model}» нет. Есть: {sample}"
    return f"🟢 работает ({settings.llm_model})"


async def check_images(settings: Settings) -> str:
    backend = settings.image_backend
    base = settings.image_api_url.rstrip("/")
    if backend == "mock":
        return "⚪ выключен (IMAGE_BACKEND=mock) — карты без арта"
    if backend == "openai":
        return f"🟢 внешний API ({settings.image_model})"
    try:
        if backend == "comfyui":
            if not await asyncio.to_thread(os.path.isfile, settings.comfy_workflow):
                return f"🔴 нет файла workflow {settings.comfy_workflow}"
            stats = await _get_json(f"{base}/system_stats")
            info = await _get_json(f"{base}/object_info/CheckpointLoaderSimple")
            names = info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
            device = ((stats.get("devices") or [{}])[0]).get("name", "GPU")
        else:  # a1111
            models = await _get_json(f"{base}/sdapi/v1/sd-models")
            names = [m.get("title", "") for m in models]
            device = "Stable Diffusion WebUI"
    except Exception as e:  # noqa: BLE001
        return f"🔴 недоступен ({base}): {type(e).__name__}"
    if not any(settings.image_model in name for name in names):
        return f"🟡 {device} работает, но модели «{settings.image_model}» нет. Есть: {', '.join(names[:5]) or '—'}"
    return f"🟢 работает ({device}, {settings.image_model})"


async def health_report(settings: Settings, payment_methods: list[str]) -> str:
    llm, images = await asyncio.gather(check_llm(settings), check_images(settings))
    labels = {"stars": "⭐ Stars", "tg_rub": "💳 рубли в Telegram", "yookassa": "💳 ЮKassa"}
    pay = ", ".join(labels.get(m, m) for m in payment_methods) or "🔴 ни одного способа"
    return f"🧠 Нейросеть: {llm}\n🎨 Художник: {images}\n💰 Оплата: {pay}"
