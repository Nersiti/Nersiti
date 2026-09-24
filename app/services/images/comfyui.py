"""ComfyUI backend (best option for the RTX 50xx series).

The workflow is stored in ComfyUI's API format (``workflows/*.json``) with placeholders:
{{prompt}} {{negative}} {{seed}} {{width}} {{height}} {{steps}} {{cfg}} {{checkpoint}}
A string that consists of a single placeholder becomes a value of the right type (number stays a number).
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from app.services.images.base import ImageError, ImageRequest

_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def substitute(obj: Any, values: dict[str, Any]) -> Any:
    if isinstance(obj, dict):
        return {k: substitute(v, values) for k, v in obj.items()}
    if isinstance(obj, list):
        return [substitute(v, values) for v in obj]
    if isinstance(obj, str):
        whole = _PLACEHOLDER.fullmatch(obj)
        if whole and whole.group(1) in values:
            return values[whole.group(1)]
        return _PLACEHOLDER.sub(lambda m: str(values.get(m.group(1), m.group(0))), obj)
    return obj


class ComfyUIBackend:
    def __init__(
        self, base_url: str, workflow_path: str, checkpoint: str, timeout: float, poll_interval: float = 1.0
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.template = json.loads(Path(workflow_path).read_text(encoding="utf-8"))
        self.checkpoint = checkpoint
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.client_id = uuid.uuid4().hex
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=15.0))

    def build_workflow(self, req: ImageRequest) -> dict[str, Any]:
        return substitute(
            self.template,
            {
                "prompt": req.prompt,
                "negative": req.negative,
                "seed": req.seed,
                "width": req.width,
                "height": req.height,
                "steps": req.steps,
                "cfg": req.cfg,
                "checkpoint": self.checkpoint,
            },
        )

    async def generate(self, req: ImageRequest) -> bytes:
        try:
            resp = await self._client.post(
                f"{self.base_url}/prompt",
                json={"prompt": self.build_workflow(req), "client_id": self.client_id},
            )
        except httpx.HTTPError as e:
            raise ImageError(f"ComfyUI is unreachable: {e!r}") from e
        if resp.status_code >= 400:
            raise ImageError(f"ComfyUI rejected workflow ({resp.status_code}): {resp.text[:800]}")
        prompt_id = resp.json()["prompt_id"]

        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            await asyncio.sleep(self.poll_interval)
            try:
                hist = await self._client.get(f"{self.base_url}/history/{prompt_id}")
            except httpx.HTTPError:
                continue
            if hist.status_code != 200:
                continue
            entry = hist.json().get(prompt_id)
            if not entry:
                continue
            status = entry.get("status") or {}
            if status.get("status_str") == "error":
                raise ImageError(f"ComfyUI execution error: {json.dumps(status)[:800]}")
            image = self._first_image(entry.get("outputs") or {})
            if image is not None:
                return await self._download(image)
            if status.get("completed"):
                raise ImageError("ComfyUI finished without an image output")
        raise ImageError("ComfyUI timeout")

    @staticmethod
    def _first_image(outputs: dict[str, Any]) -> dict[str, str] | None:
        for node_output in outputs.values():
            for image in node_output.get("images") or []:
                return image
        return None

    async def _download(self, image: dict[str, str]) -> bytes:
        params = {
            "filename": image["filename"],
            "subfolder": image.get("subfolder", ""),
            "type": image.get("type", "output"),
        }
        resp = await self._client.get(f"{self.base_url}/view", params=params)
        if resp.status_code != 200:
            raise ImageError(f"ComfyUI /view failed: {resp.status_code}")
        return resp.content

    async def close(self) -> None:
        await self._client.aclose()
