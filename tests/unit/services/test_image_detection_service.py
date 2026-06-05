import base64

import pytest

from app.errors.base import AppError
from app.models.frame_result import FrameModerationResult
from app.services.image_detection_service import ImageDetectionService


class FakeGpuService:
    async def moderate_frame_batch(self, frames):  # type: ignore[no-untyped-def]
        return [
            FrameModerationResult(
                frame_index=frames[0].frame_index,
                frame_timestamp_seconds=0.0,
                top_category="safe",
                is_nsfw=False,
                overall_severity=0,
                categories={
                    "safe": 0,
                    "suggestive": 0,
                    "nudity": 0,
                    "porn": 0,
                    "gore": 0,
                    "violence": 0,
                    "self_harm": 0,
                    "hate_or_extremism": 0,
                    "drugs": 0,
                    "unknown": 0,
                    "sexual_minor_content": 0,
                },
                reason="fixture",
                raw_response={"frame_index": 0, "top_category": "safe"},
            )
        ]


@pytest.mark.asyncio
async def test_detect_base64_returns_gpu_output(test_settings) -> None:  # type: ignore[no-untyped-def]
    service = ImageDetectionService(settings=test_settings, gpu_service=FakeGpuService())

    response = await service.detect_base64(base64.b64encode(b"image").decode("ascii"))

    assert response == {"frame_index": 0, "top_category": "safe"}


@pytest.mark.asyncio
async def test_detect_base64_rejects_invalid_input(test_settings) -> None:  # type: ignore[no-untyped-def]
    service = ImageDetectionService(settings=test_settings, gpu_service=FakeGpuService())

    with pytest.raises(AppError) as exc:
        await service.detect_base64("not base64")

    assert exc.value.code == "invalid_image_base64"


@pytest.mark.asyncio
async def test_image_service_requires_gpu(test_settings) -> None:  # type: ignore[no-untyped-def]
    service = ImageDetectionService(settings=test_settings)

    with pytest.raises(AppError) as exc:
        await service.detect_base64(base64.b64encode(b"image").decode("ascii"))

    assert exc.value.code == "gpu_not_configured"

