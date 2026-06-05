import base64
import binascii
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx

from app.config.settings import Settings
from app.errors.base import AppError
from app.services.frame_extraction_service import ExtractedFrame
from app.services.gpu_moderation_service import GpuModerationService


class ImageDetectionService:
    def __init__(
        self,
        *,
        settings: Settings,
        gpu_service: GpuModerationService | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._gpu_service = gpu_service
        self._http_client = http_client

    async def detect_url(self, image_url: str) -> dict[str, object]:
        if self._gpu_service is None:
            raise AppError("gpu_not_configured", "GPU moderation is not configured", status_code=503)

        owns_client = self._http_client is None
        client = self._http_client or httpx.AsyncClient(follow_redirects=True)
        try:
            response = await client.get(image_url, timeout=self._settings.video_download_timeout_seconds)
            response.raise_for_status()
            image_bytes = response.content
        finally:
            if owns_client:
                await client.aclose()
        return await self._detect_image_bytes(image_bytes)

    async def detect_base64(self, image_base64: str) -> dict[str, object]:
        try:
            image_bytes = base64.b64decode(image_base64, validate=True)
        except binascii.Error as exc:
            raise AppError("invalid_image_base64", "image_base64 must be valid base64") from exc
        return await self._detect_image_bytes(image_bytes)

    async def _detect_image_bytes(self, image_bytes: bytes) -> dict[str, object]:
        if self._gpu_service is None:
            raise AppError("gpu_not_configured", "GPU moderation is not configured", status_code=503)
        if not image_bytes:
            raise AppError("empty_image", "image bytes are empty")
        if len(image_bytes) > self._settings.image_max_bytes:
            raise AppError("image_too_large", "image exceeds configured max bytes")

        with TemporaryDirectory(prefix="nsfw-image-") as temp_dir:
            image_path = Path(temp_dir) / "image.jpg"
            image_path.write_bytes(image_bytes)
            results = await self._gpu_service.moderate_frame_batch(
                [ExtractedFrame(frame_index=0, timestamp_seconds=0.0, path=image_path)]
            )
        return results[0].raw_response
