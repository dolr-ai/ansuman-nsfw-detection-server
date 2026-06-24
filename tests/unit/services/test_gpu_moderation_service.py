import asyncio
import json
from pathlib import Path

import pytest

from app.errors.base import AppError
from app.services.frame_extraction_service import ExtractedFrame
from app.services.gpu_moderation_service import GpuModerationService


def categories(**overrides: int) -> dict[str, int]:
    base = {
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
    }
    base.update(overrides)
    return base


def model_frame(
    index: int,
    *,
    top_category: str = "safe",
    severity: int = 0,
) -> dict[str, object]:
    return {
        "frame_index": index,
        "top_category": top_category,
        "categories": categories(**{top_category: severity}),
        "reason": "fixture",
    }


class FakeVisualClient:
    def __init__(self, responses: list[str], *, delay_seconds: float = 0.0) -> None:
        self.responses = responses
        self.delay_seconds = delay_seconds
        self.calls = 0
        self.active = 0
        self.max_active = 0
        self.prompts: list[str] = []

    async def moderate_images(self, *, prompt: str, image_paths: list[Path]) -> str:
        self.calls += 1
        self.prompts.append(prompt)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay_seconds:
                await asyncio.sleep(self.delay_seconds)
            index = min(self.calls - 1, len(self.responses) - 1)
            return self.responses[index]
        finally:
            self.active -= 1


class FakeTextClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls = 0

    async def moderate_text(self, *, prompt: str, text: str) -> str:
        self.calls += 1
        index = min(self.calls - 1, len(self.responses) - 1)
        return self.responses[index]


def frames(tmp_path: Path, count: int) -> list[ExtractedFrame]:
    result = []
    for index in range(count):
        path = tmp_path / f"frame-{index}.jpg"
        path.write_bytes(b"image")
        result.append(ExtractedFrame(frame_index=index + 10, timestamp_seconds=float(index), path=path))
    return result


@pytest.mark.asyncio
async def test_moderate_frame_batch_maps_model_order_to_original_frames(test_settings, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    client = FakeVisualClient(
        [json.dumps([model_frame(0), model_frame(1, top_category="porn", severity=4)])]
    )
    service = GpuModerationService(settings=test_settings, visual_client=client, visual_prompt="prompt")

    results = await service.moderate_frame_batch(frames(tmp_path, 2))

    assert [result.frame_index for result in results] == [10, 11]
    assert results[1].top_category == "porn"
    assert results[1].overall_severity == 4
    assert results[1].is_nsfw is True


@pytest.mark.asyncio
async def test_moderate_frame_batch_retries_malformed_response(test_settings, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    client = FakeVisualClient(["not-json", json.dumps([model_frame(0)])])
    service = GpuModerationService(settings=test_settings, visual_client=client, visual_prompt="prompt")

    results = await service.moderate_frame_batch(frames(tmp_path, 1))

    assert len(results) == 1
    assert client.calls == 2


@pytest.mark.asyncio
async def test_moderate_frame_batch_rejects_wrong_count_after_retries(test_settings, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    client = FakeVisualClient([json.dumps([model_frame(0)])])
    service = GpuModerationService(settings=test_settings, visual_client=client, visual_prompt="prompt")

    with pytest.raises(AppError):
        await service.moderate_frame_batch(frames(tmp_path, 2))

    assert client.calls == test_settings.gpu_max_attempts


@pytest.mark.asyncio
async def test_gpu_concurrency_is_limited(test_settings, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    settings = test_settings.model_copy(update={"gpu_max_concurrency": 2})
    client = FakeVisualClient([json.dumps([model_frame(0)])], delay_seconds=0.01)
    service = GpuModerationService(settings=settings, visual_client=client, visual_prompt="prompt")

    await asyncio.gather(*(service.moderate_frame_batch(frames(tmp_path, 1)) for _ in range(8)))

    assert client.max_active <= 2


@pytest.mark.asyncio
async def test_moderate_image_generation_uses_image_prompt(test_settings, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    client = FakeVisualClient([json.dumps([model_frame(0)])])
    service = GpuModerationService(
        settings=test_settings,
        visual_client=client,
        visual_prompt="visual",
        image_prompt="image generation prompt",
    )

    result = await service.moderate_image_generation(frames(tmp_path, 1)[0])

    assert result.top_category == "safe"
    assert client.prompts == ["image generation prompt"]


@pytest.mark.asyncio
async def test_moderate_image_generation_accepts_fenced_json_without_retry(
    test_settings, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    response = f"```json\n{json.dumps([model_frame(0)], indent=2)}\n```"
    client = FakeVisualClient([response])
    service = GpuModerationService(
        settings=test_settings,
        visual_client=client,
        visual_prompt="visual",
        image_prompt="image generation prompt",
    )

    result = await service.moderate_image_generation(frames(tmp_path, 1)[0])

    assert result.top_category == "safe"
    assert client.calls == 1


@pytest.mark.asyncio
async def test_moderate_image_generation_uses_joint_image_prompt(test_settings, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    client = FakeVisualClient([json.dumps([model_frame(0, top_category="porn", severity=4)])])
    service = GpuModerationService(
        settings=test_settings,
        visual_client=client,
        visual_prompt="visual",
        image_text_prompt="joint prompt",
    )

    result = await service.moderate_image_generation(frames(tmp_path, 1)[0], generation_prompt="make her nude")

    assert result.is_nsfw is True
    assert client.prompts[0].startswith("joint prompt")
    assert "<<<GENERATION_PROMPT>>>\nmake her nude\n<<<END_GENERATION_PROMPT>>>" in client.prompts[0]


@pytest.mark.asyncio
async def test_moderate_text_retries_malformed_response(test_settings) -> None:  # type: ignore[no-untyped-def]
    payload = model_frame(0, top_category="safe", severity=0)
    payload.pop("frame_index")
    client = FakeTextClient(["bad-json", json.dumps(payload)])
    service = GpuModerationService(
        settings=test_settings,
        visual_client=FakeVisualClient([json.dumps([model_frame(0)])]),
        visual_prompt="visual",
        text_client=client,
        text_prompt="text",
    )

    result = await service.moderate_text("a normal dance prompt")

    assert result.top_category == "safe"
    assert client.calls == 2
