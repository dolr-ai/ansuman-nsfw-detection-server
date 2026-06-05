import pytest

from app.errors.base import AppError
from app.schemas.model_output import TextModerationOutput
from app.services.text_detection_service import TextDetectionService


class FakeGpuService:
    async def moderate_text(self, text: str) -> TextModerationOutput:
        return TextModerationOutput(
            top_category="safe",
            is_nsfw=False,
            should_block=False,
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
            reason="normal creative prompt",
        )


@pytest.mark.asyncio
async def test_text_detection_returns_structured_result() -> None:
    service = TextDetectionService(gpu_service=FakeGpuService())

    result = await service.detect("a normal dance video")

    assert result["top_category"] == "safe"
    assert result["should_block"] is False


@pytest.mark.asyncio
async def test_text_detection_requires_gpu() -> None:
    service = TextDetectionService()

    with pytest.raises(AppError) as exc:
        await service.detect("a normal dance video")

    assert exc.value.code == "gpu_not_configured"

