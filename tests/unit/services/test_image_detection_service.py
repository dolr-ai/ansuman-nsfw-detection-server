import base64

import httpx
import pytest

from app.errors import codes
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


class FakeHttpClient:
    def __init__(self, results: list[httpx.Response | Exception]) -> None:
        self.results = results
        self.calls = 0

    async def get(self, image_url: str, *, timeout: float) -> httpx.Response:  # noqa: ARG002
        index = min(self.calls, len(self.results) - 1)
        self.calls += 1
        result = self.results[index]
        if isinstance(result, Exception):
            raise result
        return result


def response(status_code: int, *, content: bytes = b"image") -> httpx.Response:
    return httpx.Response(status_code, content=content, request=httpx.Request("GET", "https://example.com/image.jpg"))


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
async def test_detect_url_retries_transient_download_status(test_settings) -> None:  # type: ignore[no-untyped-def]
    settings = test_settings.model_copy(
        update={"image_download_max_attempts": 2, "image_download_retry_base_delay_seconds": 0.0}
    )
    http_client = FakeHttpClient([response(503), response(200)])
    gpu_service = FakeGpuService()
    service = ImageDetectionService(settings=settings, gpu_service=gpu_service, http_client=http_client)  # type: ignore[arg-type]

    result = await service.detect_url("https://example.com/image.jpg")

    assert result.top_category == "safe"
    assert http_client.calls == 2
    assert gpu_service.generation_prompts == [None]


@pytest.mark.asyncio
async def test_detect_url_times_out_after_retries(test_settings) -> None:  # type: ignore[no-untyped-def]
    settings = test_settings.model_copy(
        update={"image_download_max_attempts": 2, "image_download_retry_base_delay_seconds": 0.0}
    )
    request = httpx.Request("GET", "https://example.com/image.jpg")
    http_client = FakeHttpClient(
        [
            httpx.ReadTimeout("download timed out", request=request),
            httpx.ReadTimeout("download timed out", request=request),
        ]
    )
    service = ImageDetectionService(settings=settings, gpu_service=FakeGpuService(), http_client=http_client)  # type: ignore[arg-type]

    with pytest.raises(AppError) as exc:
        await service.detect_url("https://example.com/image.jpg")

    assert exc.value.code == codes.IMAGE_DOWNLOAD_TIMEOUT
    assert exc.value.status_code == 504
    assert http_client.calls == 2


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
