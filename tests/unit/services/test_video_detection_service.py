from datetime import UTC, datetime

import pytest

from app.models.frame_result import FrameModerationResult
from app.models.video_job import VideoJob
from app.models.video_metadata import VideoMetadata
from app.models.video_result import VideoModerationResult
from app.repositories.kvrocks.clickhouse_buffer_repository import InMemoryClickHouseBufferRepository
from app.repositories.kvrocks.runtime_nsfw_repository import InMemoryRuntimeNsfwRepository
from app.schemas.storage_action import StorjMoveResponse
from app.services.video_detection_service import VideoDetectionService, runtime_nsfw_payload


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


def job() -> VideoJob:
    return VideoJob(
        job_id="job",
        video_id="video",
        source_object_version="",
        policy_version="nsfw_policy_v1",
        status="queued",
        publisher_user_id="user",
        post_id=None,
        canister_id=None,
        source_video_uri="https://example.com/video.mp4",
        upload_event_id=None,
        trace_id="trace",
    )


def metadata() -> VideoMetadata:
    return VideoMetadata(
        job_id="job",
        video_id="video",
        duration_seconds=1.0,
        width=64,
        height=64,
        fps=1.0,
        codec_name="h264",
        has_video_stream=True,
        frames_extracted=1,
    )


def frame(*, top_category: str = "safe", severity: int = 0, is_nsfw: bool = False) -> FrameModerationResult:
    return FrameModerationResult(
        frame_index=0,
        frame_timestamp_seconds=0.0,
        top_category=top_category,
        is_nsfw=is_nsfw,
        overall_severity=severity,
        categories=categories(**{top_category: severity}),
        reason="fixture",
        raw_response={"top_category": top_category},
    )


def result(*, move_required: bool, final_score: float, top_category: str) -> VideoModerationResult:
    now = datetime.now(UTC)
    max_category_severities = categories(**{top_category: int(final_score * 5)})
    return VideoModerationResult(
        job_id="job",
        video_id="video",
        policy_version="nsfw_policy_v1",
        prompt_version="visual_batch_moderation_v1",
        aggregation_version="hard_any_frame_v1",
        final_is_nsfw=final_score >= 0.6,
        final_score=final_score,
        final_top_category=top_category,
        max_overall_severity=int(final_score * 5),
        nsfw_frame_count=1 if final_score >= 0.6 else 0,
        total_frame_count=1,
        move_required=move_required,
        move_threshold=0.8,
        max_category_severities=max_category_severities,
        legacy_nsfw_ec="explicit" if top_category == "porn" else "neutral",
        legacy_nsfw_gore="VERY_UNLIKELY",
        final_response={"final_score": final_score},
        created_at=now,
        updated_at=now,
    )


class FakeStorageMoveService:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    async def move_if_required(self, *, result: VideoModerationResult, publisher_user_id: str):
        if not result.move_required:
            return None
        self.calls.append((publisher_user_id, result.video_id))
        if self.fail:
            raise RuntimeError("move failed")
        return StorjMoveResponse(status_code=200, body="ok")


class FakeUnitOfWork:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def __aenter__(self):
        self.events.append("tx_begin")
        return self

    async def __aexit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
        self.events.append("tx_rollback" if exc_type else "tx_commit")

    async def insert_frame_results(self, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.events.append("insert_frames")

    async def insert_final_result(self, result: VideoModerationResult) -> None:
        self.events.append("insert_result")

    async def insert_storage_action(self, action) -> None:  # type: ignore[no-untyped-def]
        self.events.append("insert_storage_action")

    async def mark_job_classified(self, job_id: str) -> None:
        self.events.append("mark_classified")


@pytest.mark.asyncio
async def test_safe_video_commits_then_publishes_without_move(test_settings) -> None:  # type: ignore[no-untyped-def]
    events: list[str] = []
    buffer = InMemoryClickHouseBufferRepository()
    runtime = InMemoryRuntimeNsfwRepository()
    service = VideoDetectionService(
        settings=test_settings,
        storage_move_service=FakeStorageMoveService(),
        unit_of_work_factory=lambda: FakeUnitOfWork(events),
        clickhouse_buffer_repository=buffer,
        runtime_repository=runtime,
    )

    await service.finalize_classification(
        job=job(),
        metadata=metadata(),
        frames=[frame()],
        result=result(move_required=False, final_score=0.0, top_category="safe"),
    )

    assert events == ["tx_begin", "insert_frames", "insert_result", "mark_classified", "tx_commit"]
    assert runtime.items["video"]["status"] == "classified"
    assert len(await buffer.read_batch(test_settings.clickhouse_buffer_video_results_key, 10)) == 1
    assert await buffer.read_batch(test_settings.clickhouse_buffer_storage_actions_key, 10) == []


@pytest.mark.asyncio
async def test_required_move_succeeds_before_commit_and_publish(test_settings) -> None:  # type: ignore[no-untyped-def]
    events: list[str] = []
    storage = FakeStorageMoveService()
    buffer = InMemoryClickHouseBufferRepository()
    service = VideoDetectionService(
        settings=test_settings.model_copy(update={"storj_interface_url": "https://storj.local"}),
        storage_move_service=storage,
        unit_of_work_factory=lambda: FakeUnitOfWork(events),
        clickhouse_buffer_repository=buffer,
        runtime_repository=InMemoryRuntimeNsfwRepository(),
    )

    finalization = await service.finalize_classification(
        job=job(),
        metadata=metadata(),
        frames=[frame(top_category="porn", severity=4, is_nsfw=True)],
        result=result(move_required=True, final_score=0.8, top_category="porn"),
    )

    assert storage.calls == [("user", "video")]
    assert finalization.storage_action is not None
    assert events == [
        "tx_begin",
        "insert_frames",
        "insert_result",
        "insert_storage_action",
        "mark_classified",
        "tx_commit",
    ]
    assert len(await buffer.read_batch(test_settings.clickhouse_buffer_storage_actions_key, 10)) == 1


@pytest.mark.asyncio
async def test_required_move_failure_prevents_transaction_and_publish(test_settings) -> None:  # type: ignore[no-untyped-def]
    events: list[str] = []
    buffer = InMemoryClickHouseBufferRepository()
    runtime = InMemoryRuntimeNsfwRepository()
    service = VideoDetectionService(
        settings=test_settings,
        storage_move_service=FakeStorageMoveService(fail=True),
        unit_of_work_factory=lambda: FakeUnitOfWork(events),
        clickhouse_buffer_repository=buffer,
        runtime_repository=runtime,
    )

    with pytest.raises(RuntimeError):
        await service.finalize_classification(
            job=job(),
            metadata=metadata(),
            frames=[frame(top_category="porn", severity=4, is_nsfw=True)],
            result=result(move_required=True, final_score=0.8, top_category="porn"),
        )

    assert events == []
    assert runtime.items == {}
    assert await buffer.read_batch(test_settings.clickhouse_buffer_video_results_key, 10) == []


def test_runtime_payload_matches_compatibility_shape() -> None:
    payload = runtime_nsfw_payload(result(move_required=True, final_score=0.8, top_category="porn"))

    assert payload == {
        "video_id": "video",
        "is_nsfw": True,
        "probability": 0.8,
        "nsfw_ec": "explicit",
        "nsfw_gore": "VERY_UNLIKELY",
        "policy_version": "nsfw_policy_v1",
        "status": "classified",
    }

