import base64

import pytest

from app.errors.base import AppError
from app.models.frame_result import FrameModerationResult
from app.services.image_detection_service import ImageDetectionService


class FakeGpuService:
    def __init__(self) -> None:
        self.generation_prompts: list[str | None] = []

    async def moderate_image_generation(self, frame, *, generation_prompt: str | None = None):  # type: ignore[no-untyped-def]
        self.generation_prompts.append(generation_prompt)
        return FrameModerationResult(
            frame_index=frame.frame_index,
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


@pytest.mark.asyncio
async def test_detect_base64_returns_gpu_output(test_settings) -> None:  # type: ignore[no-untyped-def]
    gpu_service = FakeGpuService()
    service = ImageDetectionService(settings=test_settings, gpu_service=gpu_service)

    response = await service.detect_base64(base64.b64encode(b"image").decode("ascii"))

    assert response.model_dump(mode="json") == {
        "top_category": "safe",
        "is_nsfw": False,
        "overall_severity": 0,
        "categories": {
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
        "reason": "fixture",
    }
    assert gpu_service.generation_prompts == [None]


@pytest.mark.asyncio
async def test_detect_base64_passes_non_empty_prompt(test_settings) -> None:  # type: ignore[no-untyped-def]
    gpu_service = FakeGpuService()
    service = ImageDetectionService(settings=test_settings, gpu_service=gpu_service)

    await service.detect_base64(base64.b64encode(b"image").decode("ascii"), prompt="  make her nude  ")

    assert gpu_service.generation_prompts == ["make her nude"]


@pytest.mark.asyncio
async def test_detect_base64_treats_whitespace_prompt_as_image_only(test_settings) -> None:  # type: ignore[no-untyped-def]
    gpu_service = FakeGpuService()
    service = ImageDetectionService(settings=test_settings, gpu_service=gpu_service)

    await service.detect_base64(base64.b64encode(b"image").decode("ascii"), prompt="   ")

    assert gpu_service.generation_prompts == [None]


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
