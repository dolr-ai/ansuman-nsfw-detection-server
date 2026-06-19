import asyncio
import base64
import binascii
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlsplit

import httpx

from app.config.settings import Settings
from app.core.sentry import capture_exception
from app.errors import codes
from app.errors.base import AppError
from app.models.frame_result import FrameModerationResult
from app.schemas.moderation import ModerationDetectResponse
from app.services.frame_extraction_service import ExtractedFrame
from app.services.gpu_moderation_service import GpuModerationService
from app.services.moderation_policy import compute_is_nsfw, compute_overall_severity


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

    async def detect_url(self, image_url: str, *, prompt: str | None = None) -> ModerationDetectResponse:
        if self._gpu_service is None:
            raise AppError("gpu_not_configured", "GPU moderation is not configured", status_code=503)

        owns_client = self._http_client is None
        client = self._http_client or httpx.AsyncClient(follow_redirects=True)
        try:
            image_bytes = await self._download_image_with_retries(client, image_url)
        finally:
            if owns_client:
                await client.aclose()
        return await self._detect_image_bytes(image_bytes, prompt=prompt)

    async def detect_base64(self, image_base64: str, *, prompt: str | None = None) -> ModerationDetectResponse:
        try:
            image_bytes = base64.b64decode(image_base64, validate=True)
        except binascii.Error as exc:
            raise AppError("invalid_image_base64", "image_base64 must be valid base64") from exc
        return await self._detect_image_bytes(image_bytes, prompt=prompt)

    async def _detect_image_bytes(self, image_bytes: bytes, *, prompt: str | None) -> ModerationDetectResponse:
        if self._gpu_service is None:
            raise AppError("gpu_not_configured", "GPU moderation is not configured", status_code=503)
        if not image_bytes:
            raise AppError("empty_image", "image bytes are empty")
        if len(image_bytes) > self._settings.image_max_bytes:
            raise AppError("image_too_large", "image exceeds configured max bytes")

        with TemporaryDirectory(prefix="nsfw-image-") as temp_dir:
            image_path = Path(temp_dir) / "image.jpg"
            image_path.write_bytes(image_bytes)
            result = await self._gpu_service.moderate_image_generation(
                ExtractedFrame(frame_index=0, timestamp_seconds=0.0, path=image_path),
                generation_prompt=_normalize_prompt(prompt),
            )
        return _frame_to_detect_response(result)

    async def _download_image_with_retries(self, client: httpx.AsyncClient, image_url: str) -> bytes:
        max_attempts = max(1, self._settings.image_download_max_attempts)
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                response = await client.get(image_url, timeout=self._settings.image_download_timeout_seconds)
                response.raise_for_status()
                return response.content
            except httpx.TimeoutException as exc:
                last_error = exc
                _capture_image_download_failure(
                    exc,
                    image_url=image_url,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    error_kind="timeout",
                )
                await _sleep_before_retry(
                    attempt=attempt,
                    max_attempts=max_attempts,
                    base_delay_seconds=self._settings.image_download_retry_base_delay_seconds,
                )
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status_code = exc.response.status_code
                _capture_image_download_failure(
                    exc,
                    image_url=image_url,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    error_kind="http_status",
                    status_code=status_code,
                )
                if status_code < 500:
                    raise AppError(
                        codes.IMAGE_DOWNLOAD_FAILED,
                        "image_url could not be downloaded",
                    ) from exc
                await _sleep_before_retry(
                    attempt=attempt,
                    max_attempts=max_attempts,
                    base_delay_seconds=self._settings.image_download_retry_base_delay_seconds,
                )
            except httpx.RequestError as exc:
                last_error = exc
                _capture_image_download_failure(
                    exc,
                    image_url=image_url,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    error_kind="request_error",
                )
                await _sleep_before_retry(
                    attempt=attempt,
                    max_attempts=max_attempts,
                    base_delay_seconds=self._settings.image_download_retry_base_delay_seconds,
                )

        if isinstance(last_error, httpx.TimeoutException):
            raise AppError(
                codes.IMAGE_DOWNLOAD_TIMEOUT,
                "image_url download timed out",
                status_code=504,
            ) from last_error
        if isinstance(last_error, httpx.HTTPStatusError) and last_error.response.status_code >= 500:
            raise AppError(
                codes.IMAGE_DOWNLOAD_UPSTREAM_ERROR,
                "image_url host returned an upstream error",
                status_code=502,
            ) from last_error
        if last_error is not None:
            raise AppError(codes.IMAGE_DOWNLOAD_FAILED, "image_url could not be downloaded") from last_error
        raise AppError(codes.IMAGE_DOWNLOAD_FAILED, "image_url could not be downloaded")


def _normalize_prompt(prompt: str | None) -> str | None:
    if prompt is None:
        return None
    stripped = prompt.strip()
    return stripped or None


def _frame_to_detect_response(result: FrameModerationResult) -> ModerationDetectResponse:
    return ModerationDetectResponse(
        top_category=result.top_category,
        is_nsfw=compute_is_nsfw(result.categories),
        overall_severity=compute_overall_severity(result.top_category, result.categories),
        categories=result.categories,
        reason=result.reason,
    )


async def _sleep_before_retry(*, attempt: int, max_attempts: int, base_delay_seconds: float) -> None:
    if attempt >= max_attempts or base_delay_seconds <= 0:
        return
    await asyncio.sleep(min(base_delay_seconds * (2 ** (attempt - 1)), 2.0))


def _capture_image_download_failure(
    exc: Exception,
    *,
    image_url: str,
    attempt: int,
    max_attempts: int,
    error_kind: str,
    status_code: int | None = None,
) -> None:
    capture_exception(
        exc,
        tags={
            "component": "image_detection",
            "operation": "download_image_url",
            "error_kind": error_kind,
            "retry_remaining": str(attempt < max_attempts).lower(),
        },
        context={
            "attempt": attempt,
            "max_attempts": max_attempts,
            "status_code": status_code,
            **_safe_url_context(image_url),
        },
    )


def _safe_url_context(image_url: str) -> dict[str, str | int | None]:
    parsed = urlsplit(image_url)
    return {
        "url_scheme": parsed.scheme,
        "url_host": parsed.hostname,
        "url_path": parsed.path[:160],
        "url_port": parsed.port,
    }
