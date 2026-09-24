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

TRANSLATE_PROMPT = (
    "You turn user requests into prompts for an image generation model (Stable Diffusion / Flux). "
    "Translate the request to English, keep every detail, do not add new objects. "
    "Output only the prompt text without quotes or explanations."
)


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
            "max_tokens": max_tokens or self.settings.llm_max_tokens,
            "temperature": self.settings.llm_temperature if temperature is None else temperature,
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
    """Offline stub: lets you run the bot and tests without a neural network."""

    async def complete(
        self, messages: Messages, max_tokens: int | None = None, temperature: float | None = None
    ) -> str:
        return f"Эхо: {messages[-1]['content']}"

    async def stream(self, messages: Messages) -> AsyncIterator[str]:
        for word in f"Эхо: {messages[-1]['content']}".split(" "):
            yield word + " "

    async def close(self) -> None:
        return None


def create_llm(settings: Settings) -> LLMClient:
    if settings.llm_backend == "mock":
        return MockLLM()
    return OpenAICompatLLM(settings)


async def to_image_prompt(llm: LLMClient, text: str, timeout: float = 45.0) -> str:
    """Translate a Russian description into an English prompt; on error, return it unchanged."""
    try:
        result = await asyncio.wait_for(
            llm.complete(
                [{"role": "system", "content": TRANSLATE_PROMPT}, {"role": "user", "content": text}],
                max_tokens=300,
                temperature=0.2,
            ),
            timeout,
        )
    except Exception as e:  # noqa: BLE001 - перевод не критичен
        log.warning("Prompt translation failed: %r", e)
        return text
    result = result.strip().strip('"').strip()
    return result or text
