"""Тонкий асинхронный клиент к локальному Ollama (127.0.0.1:11434).

Нейросеть подключается позже: если Ollama недоступен, методы бросают
OllamaUnavailable — вызывающий код (ai.reply) это обрабатывает и не падает.
"""
from __future__ import annotations

from typing import Any, Optional

try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None


class OllamaUnavailable(RuntimeError):
    """Ollama не запущен / модель не подключена."""


class OllamaClient:
    def __init__(self, base_url: str = "http://127.0.0.1:11434",
                 model: str = "qwen2.5:7b-instruct",
                 embed_model: str = "bge-m3",
                 temperature: float = 0.7, max_tokens: int = 512):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.embed_model = embed_model
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if httpx is None:  # pragma: no cover
            raise OllamaUnavailable("httpx не установлен")
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post(f"{self.base_url}{path}", json=payload)
                r.raise_for_status()
                return r.json()
        except Exception as e:  # соединение/таймаут/HTTP
            raise OllamaUnavailable(str(e)) from e

    async def chat(self, messages: list[dict[str, Any]],
                   tools: Optional[list[dict]] = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": self.temperature,
                        "num_predict": self.max_tokens},
        }
        if tools:
            payload["tools"] = tools
        data = await self._post("/api/chat", payload)
        return data.get("message", {})

    async def generate(self, prompt: str, system: Optional[str] = None) -> str:
        payload: dict[str, Any] = {"model": self.model, "prompt": prompt,
                                   "stream": False}
        if system:
            payload["system"] = system
        data = await self._post("/api/generate", payload)
        return data.get("response", "")

    async def embed(self, text: str) -> list[float]:
        data = await self._post("/api/embeddings",
                                {"model": self.embed_model, "prompt": text})
        return data.get("embedding", [])

    async def available(self) -> bool:
        try:
            await self._post("/api/tags", {})  # /api/tags — GET, но проверка соединения
            return True
        except OllamaUnavailable:
            return False
