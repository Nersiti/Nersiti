from __future__ import annotations

from app.config import Settings
from app.services.images.base import RATIOS, ImageBackend, ImageError, ImageRequest, build_request

__all__ = ["RATIOS", "ImageBackend", "ImageError", "ImageRequest", "build_request", "create_image_backend"]


def create_image_backend(settings: Settings) -> ImageBackend:
    if settings.image_backend == "comfyui":
        from app.services.images.comfyui import ComfyUIBackend

        return ComfyUIBackend(
            settings.image_api_url, settings.comfy_workflow, settings.image_model, settings.image_timeout
        )
    if settings.image_backend == "a1111":
        from app.services.images.others import A1111Backend

        return A1111Backend(settings.image_api_url, settings.image_sampler, settings.image_timeout)
    if settings.image_backend == "openai":
        from app.services.images.others import OpenAIImagesBackend

        return OpenAIImagesBackend(
            settings.image_api_url,
            settings.image_api_key.get_secret_value(),
            settings.image_model,
            settings.image_timeout,
        )
    from app.services.images.others import MockImageBackend

    return MockImageBackend()
