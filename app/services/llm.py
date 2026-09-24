"""Client for any OpenAI-compatible chat API: Ollama, LM Studio, vLLM, DeepSeek, OpenRouter, VseGPT..."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Protocol

import httpx

from app.config import Settings
from app.services.formatting import strip_think

log = logging.getLogger(__name__)

Messages = list[dict[str, str]]

class LLMError(RuntimeError):
    pass


class LLMClient(Protocol):
    async def complete(self, messages: Messages, max_tokens: int | None = None, temperature: float | None = None) -> str: ...

    def stream(self, messages: Messages) -> AsyncIterator[str]: ...

    async def close(self) -> None: ...


class OpenAICompatLLM:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._url = settings.llm_base_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        key = settings.llm_api_key.get_secret_value()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        self._client = httpx.AsyncClient(
            headers=headers, timeout=httpx.Timeout(settings.llm_timeout, connect=15.0)
        )
        self._sem = asyncio.Semaphore(max(settings.llm_concurrency, 1))

    def _payload(self, messages: Messages, max_tokens: int | None, temperature: float | None, stream: bool) -> dict:
        return {
            "model": self.settings.llm_model,
            "messages": messages,
            "max_tokens": max_tokens or 800,
            "temperature": 0.8 if temperature is None else temperature,
            "stream": stream,
        }

    async def complete(
        self, messages: Messages, max_tokens: int | None = None, temperature: float | None = None
    ) -> str:
        async with self._sem:
            try:
                resp = await self._client.post(self._url, json=self._payload(messages, max_tokens, temperature, False))
            except httpx.HTTPError as e:
                raise LLMError(f"LLM request failed: {e!r}") from e
        if resp.status_code >= 400:
            raise LLMError(f"LLM HTTP {resp.status_code}: {resp.text[:500]}")
        try:
            content = resp.json()["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, ValueError) as e:
            raise LLMError(f"Unexpected LLM response: {resp.text[:500]}") from e
        return strip_think(content).strip()

    async def stream(self, messages: Messages) -> AsyncIterator[str]:
        """Yields text chunks as they arrive."""
        payload = self._payload(messages, None, None, True)
        async with self._sem:
            try:
                async with self._client.stream("POST", self._url, json=payload) as resp:
                    if resp.status_code >= 400:
                        body = (await resp.aread()).decode(errors="replace")
                        raise LLMError(f"LLM HTTP {resp.status_code}: {body[:500]}")
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except ValueError:
                            continue
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        piece = (choices[0].get("delta") or {}).get("content")
                        if piece:
                            yield piece
            except httpx.HTTPError as e:
                raise LLMError(f"LLM stream failed: {e!r}") from e

    async def close(self) -> None:
        await self._client.aclose()


class MockLLM:
    """No neural network: returns an empty answer, and the game falls back to templates."""

    async def complete(
        self, messages: Messages, max_tokens: int | None = None, temperature: float | None = None
    ) -> str:
        return ""

    async def stream(self, messages: Messages) -> AsyncIterator[str]:
        return
        yield ""  # pragma: no cover — делает функцию асинхронным генератором

    async def close(self) -> None:
        return None


def create_llm(settings: Settings) -> LLMClient:
    if settings.llm_backend == "mock":
        return MockLLM()
    return OpenAICompatLLM(settings)
