import asyncio
from pathlib import Path
from typing import Protocol

from app.config.settings import Settings
from app.models.frame_result import FrameModerationResult
from app.schemas.model_output import TextModerationOutput, parse_text_moderation_response, parse_visual_batch_response
from app.services.frame_extraction_service import ExtractedFrame


class VisualModerationClient(Protocol):
    async def moderate_images(self, *, prompt: str, image_paths: list[Path]) -> str:
        ...


class TextModerationClient(Protocol):
    async def moderate_text(self, *, prompt: str, text: str) -> str:
        ...


class GpuModerationService:
    def __init__(
        self,
        *,
        settings: Settings,
        visual_client: VisualModerationClient,
        visual_prompt: str,
        text_client: TextModerationClient | None = None,
        text_prompt: str | None = None,
    ) -> None:
        self._settings = settings
        self._visual_client = visual_client
        self._visual_prompt = visual_prompt
        self._text_client = text_client
        self._text_prompt = text_prompt
        self._semaphore = asyncio.Semaphore(settings.gpu_max_concurrency)

    async def moderate_frame_batch(self, frames: list[ExtractedFrame]) -> list[FrameModerationResult]:
        if not frames:
            return []
        if len(frames) > self._settings.frame_batch_size:
            raise ValueError("frame batch is larger than configured batch size")

        last_error: Exception | None = None
        image_paths = [frame.path for frame in frames]
        for _ in range(self._settings.gpu_max_attempts):
            try:
                async with self._semaphore:
                    raw_response = await self._visual_client.moderate_images(
                        prompt=self._visual_prompt,
                        image_paths=image_paths,
                    )
                parsed = parse_visual_batch_response(raw_response, expected_count=len(frames))
                return [
                    FrameModerationResult(
                        frame_index=frames[index].frame_index,
                        frame_timestamp_seconds=frames[index].timestamp_seconds,
                        top_category=item.top_category,
                        is_nsfw=item.is_nsfw,
                        overall_severity=item.overall_severity,
                        categories=item.categories,
                        reason=item.reason,
                        raw_response=item.model_dump(mode="json"),
                    )
                    for index, item in enumerate(parsed)
                ]
            except Exception as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise RuntimeError("GPU moderation failed without an exception")

    async def moderate_text(self, text: str) -> TextModerationOutput:
        if self._text_client is None or self._text_prompt is None:
            raise RuntimeError("text moderation client is not configured")

        last_error: Exception | None = None
        for _ in range(self._settings.gpu_max_attempts):
            try:
                async with self._semaphore:
                    raw_response = await self._text_client.moderate_text(prompt=self._text_prompt, text=text)
                return parse_text_moderation_response(raw_response)
            except Exception as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise RuntimeError("text moderation failed without an exception")
