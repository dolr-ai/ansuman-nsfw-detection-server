from dataclasses import dataclass, replace

import httpx

from app.config.settings import Settings
from app.core.constants import TERMINAL_VIDEO_STATUSES, VideoJobStatus
from app.errors import codes
from app.errors.base import AppError
from app.models.video_job import VideoJob
from app.repositories.postgres.video_finalization import VideoJobStateRepository
from app.services.aggregation_service import AggregationService
from app.services.frame_extraction_service import FrameExtractionService, download_video, frame_batches, job_temp_dir
from app.services.gpu_moderation_service import GpuModerationService
from app.services.queue_service import QueueService
from app.services.video_detection_service import VideoDetectionService
from app.utils.file_cleanup import cleanup_dir

TERMINAL_PROCESSING_ERROR_CODES = {
    codes.VIDEO_DOWNLOAD_EMPTY,
    codes.VIDEO_TOO_LARGE,
    codes.VIDEO_NO_STREAM,
    codes.VIDEO_PROBE_FAILED,
    codes.VIDEO_EXTRACTION_FAILED,
}


@dataclass(frozen=True)
class ProcessingFailure:
    status: VideoJobStatus
    error_code: str
    error_message: str
    retryable: bool


class VideoJobProcessingError(Exception):
    def __init__(self, failure: ProcessingFailure) -> None:
        super().__init__(failure.error_message)
        self.failure = failure


class VideoJobProcessor:
    def __init__(
        self,
        *,
        settings: Settings,
        queue_service: QueueService,
        job_state_repository: VideoJobStateRepository,
        frame_extraction_service: FrameExtractionService,
        gpu_service: GpuModerationService,
        aggregation_service: AggregationService,
        detection_service: VideoDetectionService,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._queue_service = queue_service
        self._job_state_repository = job_state_repository
        self._frame_extraction_service = frame_extraction_service
        self._gpu_service = gpu_service
        self._aggregation_service = aggregation_service
        self._detection_service = detection_service
        self._http_client = http_client

    async def process(self, job: VideoJob) -> None:
        current_job = await self._queue_service.get_status_by_job_id(job.job_id) or job
        if current_job.status in TERMINAL_VIDEO_STATUSES:
            return

        persisted_job = await self._job_state_repository.get_by_job_id(job.job_id)
        if persisted_job is not None and persisted_job.status == VideoJobStatus.CLASSIFIED:
            await self._queue_service.update_status(job.job_id, VideoJobStatus.CLASSIFIED)
            return

        processing_job = await self._queue_service.update_status(job.job_id, VideoJobStatus.PROCESSING) or current_job
        try:
            await self._job_state_repository.mark_processing(processing_job)
            await self._process_video(processing_job)
        except Exception as exc:
            failure = classify_processing_error(
                exc,
                attempts=processing_job.attempts,
                max_attempts=self._settings.queue_max_attempts,
            )
            await self._queue_service.update_status(
                processing_job.job_id,
                failure.status,
                last_error_code=failure.error_code,
                last_error_message=failure.error_message,
            )
            await self._job_state_repository.mark_failed(
                processing_job.job_id,
                status=failure.status,
                error_code=failure.error_code,
                error_message=failure.error_message,
            )
            raise VideoJobProcessingError(failure) from exc

    async def _process_video(self, job: VideoJob) -> None:
        job_dir = await self._frame_extraction_service.prepare_job_dir(job.job_id)
        source_path = job_dir / "source.mp4"
        try:
            await download_video(job.source_video_uri, source_path, self._settings, self._http_client)
            metadata = await self._frame_extraction_service.probe(
                job_id=job.job_id,
                video_id=job.video_id,
                source_path=source_path,
            )
            extracted_frames = await self._frame_extraction_service.extract_frames(source_path, job_dir / "frames")
            metadata = replace(metadata, frames_extracted=len(extracted_frames))

            frame_results = []
            for batch in frame_batches(extracted_frames, self._settings.frame_batch_size):
                frame_results.extend(await self._gpu_service.moderate_frame_batch(batch))

            final_result = self._aggregation_service.aggregate(
                job_id=job.job_id,
                video_id=job.video_id,
                policy_version=job.policy_version,
                frames=frame_results,
            )
            await self._detection_service.finalize_classification(
                job=job,
                metadata=metadata,
                frames=frame_results,
                result=final_result,
            )
            await self._queue_service.update_status(job.job_id, VideoJobStatus.CLASSIFIED)
        finally:
            cleanup_dir(job_temp_dir(job.job_id, self._settings))


def classify_processing_error(exc: Exception, *, attempts: int, max_attempts: int) -> ProcessingFailure:
    error_code = _error_code(exc)
    error_message = _error_message(exc)
    retryable = _is_retryable(exc) and attempts < max_attempts
    status = VideoJobStatus.FAILED_RETRYABLE if retryable else VideoJobStatus.FAILED_TERMINAL
    return ProcessingFailure(
        status=status,
        error_code=error_code,
        error_message=error_message,
        retryable=retryable,
    )


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        return status_code in {408, 429} or status_code >= 500
    if isinstance(exc, httpx.RequestError):
        return True
    if isinstance(exc, AppError):
        return exc.code not in TERMINAL_PROCESSING_ERROR_CODES and exc.status_code >= 500
    return True


def _error_code(exc: Exception) -> str:
    if isinstance(exc, AppError):
        return exc.code
    if isinstance(exc, httpx.HTTPStatusError):
        return f"http_{exc.response.status_code}"
    return exc.__class__.__name__


def _error_message(exc: Exception) -> str:
    if isinstance(exc, AppError):
        message = exc.message
    else:
        message = str(exc) or exc.__class__.__name__
    return message[:1000]
