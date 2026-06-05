from datetime import UTC, datetime

import pytest

from app.repositories.kvrocks.clickhouse_buffer_repository import InMemoryClickHouseBufferRepository
from app.services.clickhouse_flush_service import ClickHouseFlushService


class RecordingRepository:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, list[object]]] = []

    def insert_rows(self, table_name: str, rows: list[object]) -> None:
        if self.fail:
            raise RuntimeError("insert failed")
        self.calls.append((table_name, rows))


def video_row(now: datetime) -> dict[str, object]:
    return {
        "video_id": "video",
        "job_id": "job",
        "publisher_user_id": "user",
        "post_id": None,
        "canister_id": None,
        "source_video_uri": "https://example.com/video.mp4",
        "source_object_version": "",
        "upload_event_id": None,
        "status": "classified",
        "policy_version": "nsfw_policy_v1",
        "prompt_version": "visual_batch_moderation_v1",
        "aggregation_version": "hard_any_frame_v1",
        "model_provider": "openai-compatible",
        "model_name": "model",
        "model_version": None,
        "duration_seconds": 1.0,
        "frames_extracted": 1,
        "frames_processed": 1,
        "frame_batch_size": 5,
        "final_is_nsfw": True,
        "final_score": 0.8,
        "final_top_category": "porn",
        "max_overall_severity": 4,
        "nsfw_frame_count": 1,
        "total_frame_count": 1,
        "max_suggestive_severity": 0,
        "max_nudity_severity": 0,
        "max_porn_severity": 4,
        "max_gore_severity": 0,
        "max_violence_severity": 0,
        "max_self_harm_severity": 0,
        "max_hate_or_extremism_severity": 0,
        "max_drugs_severity": 0,
        "max_unknown_severity": 0,
        "max_sexual_minor_content_severity": 0,
        "move_required": True,
        "move_threshold": 0.8,
        "storj_move_status": "succeeded",
        "legacy_nsfw_ec": "explicit",
        "legacy_nsfw_gore": "VERY_UNLIKELY",
        "frame_results_json": "[]",
        "final_response_json": "{}",
        "created_at": now,
        "updated_at": now,
        "updated_at_replacing": now,
    }


@pytest.mark.asyncio
async def test_flush_trims_video_buffer_after_success(test_settings) -> None:  # type: ignore[no-untyped-def]
    now = datetime.now(UTC)
    buffer = InMemoryClickHouseBufferRepository()
    await buffer.push_json(test_settings.clickhouse_buffer_video_results_key, video_row(now))
    video_repo = RecordingRepository()
    service = ClickHouseFlushService(
        settings=test_settings,
        buffer_repository=buffer,
        video_result_repository=video_repo,
        legacy_repository=RecordingRepository(),
        storage_action_repository=RecordingRepository(),
    )

    await service.flush_once()

    assert len(video_repo.calls) == 1
    assert await buffer.read_batch(test_settings.clickhouse_buffer_video_results_key, 10) == []


@pytest.mark.asyncio
async def test_flush_keeps_buffer_after_insert_failure(test_settings) -> None:  # type: ignore[no-untyped-def]
    now = datetime.now(UTC)
    buffer = InMemoryClickHouseBufferRepository()
    await buffer.push_json(test_settings.clickhouse_buffer_video_results_key, video_row(now))
    service = ClickHouseFlushService(
        settings=test_settings,
        buffer_repository=buffer,
        video_result_repository=RecordingRepository(fail=True),
        legacy_repository=RecordingRepository(),
        storage_action_repository=RecordingRepository(),
    )

    with pytest.raises(RuntimeError):
        await service.flush_once()

    assert len(await buffer.read_batch(test_settings.clickhouse_buffer_video_results_key, 10)) == 1

