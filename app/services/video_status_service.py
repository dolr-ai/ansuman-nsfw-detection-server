from collections.abc import Callable
from typing import Any, Protocol

from app.core.constants import VideoJobStatus
from app.models.video_job import VideoJob
from app.models.video_result import VideoModerationResult
from app.repositories.postgres.video_result_repository import VideoResultRepository
from app.schemas.video import VideoFinalResultResponse, VideoStatusResponse


class VideoJobReader(Protocol):
    async def get_status_by_video_id(self, video_id: str) -> VideoJob | None:
        ...


class VideoResultReader(Protocol):
    async def get_by_job_id(self, job_id: str) -> VideoModerationResult | None:
        ...

    async def get_latest_by_video_id(self, video_id: str) -> VideoModerationResult | None:
        ...


class PostgresVideoResultReader:
    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory

    async def get_by_job_id(self, job_id: str) -> VideoModerationResult | None:
        async with self._session_factory() as session:
            return await VideoResultRepository(session).get_by_job_id(job_id)

    async def get_latest_by_video_id(self, video_id: str) -> VideoModerationResult | None:
        async with self._session_factory() as session:
            return await VideoResultRepository(session).get_latest_by_video_id(video_id)


class VideoStatusService:
    def __init__(
        self,
        *,
        queue_service: VideoJobReader,
        result_reader: VideoResultReader | None = None,
    ) -> None:
        self._queue_service = queue_service
        self._result_reader = result_reader

    async def get_status_by_video_id(self, video_id: str) -> VideoStatusResponse | None:
        job = await self._queue_service.get_status_by_video_id(video_id)
        if job is None:
            return await self._classified_status_from_result(video_id)

        final_result = None
        if job.status == VideoJobStatus.CLASSIFIED and self._result_reader is not None:
            final_result = await self._result_reader.get_by_job_id(job.job_id)

        return VideoStatusResponse(
            job_id=job.job_id,
            video_id=job.video_id,
            status=job.status,
            trace_id=job.trace_id,
            attempts=job.attempts,
            last_error_code=job.last_error_code,
            last_error_message=job.last_error_message,
            final_result=final_result_response(final_result) if final_result is not None else None,
        )

    async def _classified_status_from_result(self, video_id: str) -> VideoStatusResponse | None:
        if self._result_reader is None:
            return None

        result = await self._result_reader.get_latest_by_video_id(video_id)
        if result is None:
            return None

        return VideoStatusResponse(
            job_id=result.job_id,
            video_id=result.video_id,
            status=VideoJobStatus.CLASSIFIED,
            final_result=final_result_response(result),
        )


def final_result_response(result: VideoModerationResult) -> VideoFinalResultResponse:
    return VideoFinalResultResponse(
        policy_version=result.policy_version,
        prompt_version=result.prompt_version,
        aggregation_version=result.aggregation_version,
        final_is_nsfw=result.final_is_nsfw,
        final_score=result.final_score,
        final_top_category=result.final_top_category,
        max_overall_severity=result.max_overall_severity,
        nsfw_frame_count=result.nsfw_frame_count,
        total_frame_count=result.total_frame_count,
        move_required=result.move_required,
        move_threshold=result.move_threshold,
        max_category_severities=result.max_category_severities,
        legacy_nsfw_ec=result.legacy_nsfw_ec,
        legacy_nsfw_gore=result.legacy_nsfw_gore,
        final_response=result.final_response,
    )
