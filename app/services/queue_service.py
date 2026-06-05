from app.models.video_job import VideoJob
from app.repositories.kvrocks.queue_repository import EnqueueResult, VideoQueueRepository
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

