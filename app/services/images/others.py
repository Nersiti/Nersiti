"""Other generation backends: Automatic1111/Forge, OpenAI-compatible Images API, and an offline stub."""

from __future__ import annotations

import base64
import struct
import zlib

import httpx

from app.services.images.base import ImageError, ImageRequest


class A1111Backend:
    """Stable Diffusion WebUI (A1111 / Forge / SD.Next) started with the --api flag."""

    def __init__(self, base_url: str, sampler: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.sampler = sampler
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=15.0))

    async def generate(self, req: ImageRequest) -> bytes:
        payload = {
            "prompt": req.prompt,
            "negative_prompt": req.negative,
            "width": req.width,
            "height": req.height,
            "steps": req.steps,
            "cfg_scale": req.cfg,
            "seed": req.seed,
            "sampler_name": self.sampler,
            "batch_size": 1,
            "n_iter": 1,
        }
        try:
            resp = await self._client.post(f"{self.base_url}/sdapi/v1/txt2img", json=payload)
        except httpx.HTTPError as e:
            raise ImageError(f"A1111 is unreachable: {e!r}") from e
        if resp.status_code >= 400:
            raise ImageError(f"A1111 HTTP {resp.status_code}: {resp.text[:500]}")
        images = resp.json().get("images") or []
        if not images:
            raise ImageError("A1111 returned no images")
        return base64.b64decode(images[0].split(",", 1)[-1])

    async def close(self) -> None:
        await self._client.aclose()


class OpenAIImagesBackend:
    """Any OpenAI-compatible /images/generations (for when there's no local GPU)."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout: float) -> None:
        self.url = base_url.rstrip("/") + "/images/generations"
        self.model = model
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(timeout, connect=15.0))

    def _size(self, req: ImageRequest) -> str:
        wide = self.model.startswith("dall-e-3")
        if req.width > req.height * 1.15:
            return "1792x1024" if wide else "1536x1024"
        if req.height > req.width * 1.15:
            return "1024x1792" if wide else "1024x1536"
        return "1024x1024"

    async def generate(self, req: ImageRequest) -> bytes:
        payload: dict[str, object] = {"model": self.model, "prompt": req.prompt, "n": 1, "size": self._size(req)}
        if not self.model.startswith("gpt-image"):
            payload["response_format"] = "b64_json"
        try:
            resp = await self._client.post(self.url, json=payload)
        except httpx.HTTPError as e:
            raise ImageError(f"Images API is unreachable: {e!r}") from e
        if resp.status_code >= 400:
            raise ImageError(f"Images API HTTP {resp.status_code}: {resp.text[:500]}")
        data = (resp.json().get("data") or [{}])[0]
        if data.get("b64_json"):
            return base64.b64decode(data["b64_json"])
        if data.get("url"):
            img = await self._client.get(data["url"])
            img.raise_for_status()
            return img.content
        raise ImageError("Images API returned no image")

    async def close(self) -> None:
        await self._client.aclose()


class MockImageBackend:
    """Draws a gradient (seed-dependent) — for tests and running without a GPU."""

    async def generate(self, req: ImageRequest) -> bytes:
        return gradient_png(256, int(256 * req.height / req.width), req.seed)

    async def close(self) -> None:
        return None


def gradient_png(width: int, height: int, seed: int) -> bytes:
    r0, g0, b0 = seed % 256, (seed // 256) % 256, (seed // 65536) % 256
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            rows += bytes(((r0 + x) % 256, (g0 + y) % 256, (b0 + x + y) % 256))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(rows), 6))
        + chunk(b"IEND", b"")
    )
