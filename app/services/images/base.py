from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Protocol

from app.config import Settings


class ImageError(RuntimeError):
    pass


@dataclass(frozen=True)
class Style:
    label: str
    positive: str
    negative: str = ""


STYLES: dict[str, Style] = {
    "auto": Style("✨ Авто", "high quality, highly detailed, beautiful composition"),
    "photo": Style(
        "📷 Фото",
        "photorealistic, 35mm photograph, natural lighting, sharp focus, highly detailed, 8k",
        "cartoon, illustration, painting, drawing, anime, 3d render",
    ),
    "anime": Style(
        "🌸 Аниме",
        "anime style, key visual, vibrant colors, clean lineart, detailed illustration",
        "photo, realistic, 3d render",
    ),
    "art": Style("🖼 Арт", "digital painting, concept art, dramatic lighting, masterpiece, trending on artstation"),
    "3d": Style("🧸 3D", "3d render, octane render, pixar style, soft studio lighting, cute, highly detailed"),
    "cyber": Style("🌆 Киберпанк", "cyberpunk, neon lights, futuristic, cinematic lighting, rain, high detail"),
    "oil": Style("🎨 Масло", "oil painting, visible brush strokes, impressionism, rich colors, canvas texture"),
    "logo": Style(
        "🔷 Лого",
        "minimalist vector logo, flat design, simple geometric shapes, white background, professional branding",
        "photo, realistic, gradient, watermark",
    ),
}

# code -> (подпись, ширина, высота) — разрешения SDXL/Flux
RATIOS: dict[str, tuple[str, int, int]] = {
    "1x1": ("⬛ 1:1", 1024, 1024),
    "2x3": ("📱 2:3", 832, 1216),
    "3x2": ("🖼 3:2", 1216, 832),
    "9x16": ("📲 9:16", 768, 1344),
    "16x9": ("🖥 16:9", 1344, 768),
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


def build_request(
    settings: Settings, prompt: str, style_code: str = "auto", ratio_code: str = "1x1", seed: int | None = None
) -> ImageRequest:
    style = STYLES.get(style_code, STYLES["auto"])
    _, width, height = RATIOS.get(ratio_code, RATIOS["1x1"])
    scale = settings.image_size_scale
    positive = f"{prompt}, {style.positive}" if style.positive else prompt
    negative = ", ".join(x for x in (settings.image_negative, style.negative) if x)
    return ImageRequest(
        prompt=positive,
        negative=negative,
        width=_round8(width * scale),
        height=_round8(height * scale),
        seed=seed if seed is not None else random.randint(1, 2**31 - 1),
        steps=settings.image_steps,
        cfg=settings.image_cfg,
    )
