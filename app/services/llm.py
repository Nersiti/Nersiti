"""Client for any OpenAI-compatible chat API: Ollama, LM Studio, vLLM, DeepSeek, OpenRouter, VseGPT..."""

from __future__ import annotations

import asyncio
from typing import Protocol

import httpx

from app.config import Settings
from app.services.formatting import strip_think

Messages = list[dict[str, str]]


class LLMError(RuntimeError):
    pass


class LLMClient(Protocol):
    async def complete(
        self, messages: Messages, max_tokens: int | None = None, temperature: float | None = None
    ) -> str: ...

    async def close(self) -> None: ...


class OpenAICompatLLM:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._url = settings.llm_base_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if key := settings.llm_api_key.get_secret_value():
            headers["Authorization"] = f"Bearer {key}"
        self._client = httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(settings.llm_timeout, connect=15.0))
        self._sem = asyncio.Semaphore(max(settings.llm_concurrency, 1))

    async def complete(
        self, messages: Messages, max_tokens: int | None = None, temperature: float | None = None
    ) -> str:
        payload = {
            "model": self.settings.llm_model,
            "messages": messages,
            "max_tokens": max_tokens or 800,
            "temperature": 0.8 if temperature is None else temperature,
            "stream": False,
        }
        async with self._sem:
            try:
                resp = await self._client.post(self._url, json=payload)
            except httpx.HTTPError as e:
                raise LLMError(f"LLM request failed: {e!r}") from e
        if resp.status_code >= 400:
            raise LLMError(f"LLM HTTP {resp.status_code}: {resp.text[:500]}")
        try:
            content = resp.json()["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, ValueError) as e:
            raise LLMError(f"Unexpected LLM response: {resp.text[:500]}") from e
        return strip_think(content).strip()

    async def close(self) -> None:
        await self._client.aclose()


class MockLLM:
    """No neural network: returns an empty answer, and the game falls back to templates."""

    async def complete(
        self, messages: Messages, max_tokens: int | None = None, temperature: float | None = None
    ) -> str:
        return ""

    async def close(self) -> None:
        return None


def create_llm(settings: Settings) -> LLMClient:
    if settings.llm_backend == "mock":
        return MockLLM()
    return OpenAICompatLLM(settings)
