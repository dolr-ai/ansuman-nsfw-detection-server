from app.core.constants import VideoJobStatus
from app.models.video_job import VideoJob
from app.repositories.kvrocks.queue_repository import EnqueueResult, QueuedVideoJobMessage, VideoQueueRepository
from app.schemas.video import VideoDetectRequest


class QueueService:
    def __init__(self, queue_repository: VideoQueueRepository) -> None:
        self._queue_repository = queue_repository

    async def enqueue_video_detection(self, request: VideoDetectRequest) -> EnqueueResult:
        return await self._queue_repository.enqueue_video_job(request)

    async def get_status_by_video_id(self, video_id: str) -> VideoJob | None:
        return await self._queue_repository.get_job_by_video_id(video_id)

    async def get_status_by_job_id(self, job_id: str) -> VideoJob | None:
        return await self._queue_repository.get_job_by_id(job_id)

    async def update_status(
        self,
        job_id: str,
        status: VideoJobStatus,
        *,
        last_error_code: str | None = None,
        last_error_message: str | None = None,
    ) -> VideoJob | None:
        return await self._queue_repository.update_status(
            job_id,
            status,
            last_error_code=last_error_code,
            last_error_message=last_error_message,
        )

    async def ensure_consumer_group(self) -> None:
        await self._queue_repository.ensure_consumer_group()

    async def read_video_job_messages(
        self,
        *,
        consumer_name: str,
        count: int,
        block_ms: int,
    ) -> list[QueuedVideoJobMessage]:
        return await self._queue_repository.read_video_job_messages(
            consumer_name=consumer_name,
            count=count,
            block_ms=block_ms,
        )

    async def ack_video_job_message(self, message_id: str) -> None:
        await self._queue_repository.ack_video_job_message(message_id)

    async def requeue_video_job(self, job_id: str) -> None:
        await self._queue_repository.requeue_video_job(job_id)

    async def move_video_job_message_to_dlq(
        self,
        message: QueuedVideoJobMessage,
        *,
        error_code: str,
        error_message: str,
    ) -> None:
        await self._queue_repository.move_video_job_message_to_dlq(
            message,
            error_code=error_code,
            error_message=error_message,
        )
