from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Protocol

from app.config import Settings


class ImageError(RuntimeError):
    pass


QUALITY = "high quality, highly detailed, beautiful composition"

# code -> (ширина, высота) — разрешения, на которых обучены SDXL/Flux
RATIOS: dict[str, tuple[int, int]] = {
    "1x1": (1024, 1024),
    "3x2": (1216, 832),
    "2x3": (832, 1216),
}


@dataclass(frozen=True)
class ImageRequest:
    prompt: str
    negative: str
    width: int
    height: int
    seed: int
    steps: int
    cfg: float


class ImageBackend(Protocol):
    async def generate(self, req: ImageRequest) -> bytes: ...

    async def close(self) -> None: ...


def _round8(value: float) -> int:
    return max(256, round(value / 8) * 8)


def build_request(settings: Settings, prompt: str, ratio: str = "1x1", seed: int | None = None) -> ImageRequest:
    width, height = RATIOS.get(ratio, RATIOS["1x1"])
    scale = settings.image_size_scale
    return ImageRequest(
        prompt=f"{prompt}, {QUALITY}",
        negative=settings.image_negative,
        width=_round8(width * scale),
        height=_round8(height * scale),
        seed=seed if seed is not None else random.randint(1, 2**31 - 1),
        steps=settings.image_steps,
        cfg=settings.image_cfg,
    )
