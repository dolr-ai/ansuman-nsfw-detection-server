from datetime import UTC, datetime

import pytest

from app.core.constants import VideoJobStatus
from app.models.video_job import VideoJob
from app.models.video_result import VideoModerationResult
from app.services.video_status_service import VideoStatusService


def job(status: VideoJobStatus) -> VideoJob:
    return VideoJob(
        job_id="job",
        video_id="video",
        source_object_version="",
        policy_version="nsfw_policy_v1",
        status=status,
        publisher_user_id="user",
        post_id=None,
        canister_id=None,
        source_video_uri="https://example.com/video.mp4",
        upload_event_id=None,
        trace_id="trace",
        attempts=1,
    )


def result() -> VideoModerationResult:
    now = datetime.now(UTC)
    return VideoModerationResult(
        job_id="job",
        video_id="video",
        policy_version="nsfw_policy_v1",
        prompt_version="visual_batch_moderation_v1",
        aggregation_version="hard_any_frame_v1",
        final_is_nsfw=True,
        final_score=0.8,
        final_top_category="porn",
        max_overall_severity=4,
        nsfw_frame_count=1,
        total_frame_count=5,
        move_required=True,
        move_threshold=0.8,
        max_category_severities={"porn": 4},
        legacy_nsfw_ec="explicit",
        legacy_nsfw_gore="VERY_UNLIKELY",
        final_response={"final_is_nsfw": True},
        created_at=now,
        updated_at=now,
    )


class FakeQueueService:
    def __init__(self, video_job: VideoJob | None) -> None:
        self.video_job = video_job

    async def get_status_by_video_id(self, video_id: str) -> VideoJob | None:
        assert video_id == "video"
        return self.video_job


class FakeResultReader:
    def __init__(self, final_result: VideoModerationResult | None) -> None:
        self.final_result = final_result
        self.job_id_calls: list[str] = []
        self.video_id_calls: list[str] = []

    async def get_by_job_id(self, job_id: str) -> VideoModerationResult | None:
        self.job_id_calls.append(job_id)
        return self.final_result

    async def get_latest_by_video_id(self, video_id: str) -> VideoModerationResult | None:
        self.video_id_calls.append(video_id)
        return self.final_result


@pytest.mark.asyncio
async def test_queued_status_does_not_query_final_result() -> None:
    reader = FakeResultReader(result())
    service = VideoStatusService(
        queue_service=FakeQueueService(job(VideoJobStatus.QUEUED)),
        result_reader=reader,
    )

    response = await service.get_status_by_video_id("video")

    assert response is not None
    assert response.status == VideoJobStatus.QUEUED
    assert response.final_result is None
    assert reader.job_id_calls == []
    assert reader.video_id_calls == []


@pytest.mark.asyncio
async def test_classified_status_includes_final_result() -> None:
    reader = FakeResultReader(result())
    service = VideoStatusService(
        queue_service=FakeQueueService(job(VideoJobStatus.CLASSIFIED)),
        result_reader=reader,
    )

    response = await service.get_status_by_video_id("video")

    assert response is not None
    assert response.status == VideoJobStatus.CLASSIFIED
    assert response.final_result is not None
    assert response.final_result.final_score == 0.8
    assert response.final_result.max_category_severities == {"porn": 4}
    assert reader.job_id_calls == ["job"]


@pytest.mark.asyncio
async def test_status_falls_back_to_latest_final_result_when_queue_job_is_missing() -> None:
    reader = FakeResultReader(result())
    service = VideoStatusService(
        queue_service=FakeQueueService(None),
        result_reader=reader,
    )

    response = await service.get_status_by_video_id("video")

    assert response is not None
    assert response.job_id == "job"
    assert response.status == VideoJobStatus.CLASSIFIED
    assert response.final_result is not None
    assert reader.video_id_calls == ["video"]
