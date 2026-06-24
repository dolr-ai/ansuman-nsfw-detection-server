import asyncio
import logging
import os
import socket

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.clients.http import create_http_client
from app.clients.kvrocks import create_kvrocks_client
from app.clients.postgres import create_postgres_engine
from app.clients.storj_interface import StorjInterfaceClient
from app.config.logging import configure_logging
from app.config.settings import Settings
from app.core.lifecycle import build_gpu_moderation_service
from app.repositories.kvrocks.clickhouse_buffer_repository import RedisClickHouseBufferRepository
from app.repositories.kvrocks.queue_repository import QueuedVideoJobMessage, RedisVideoQueueRepository
from app.repositories.kvrocks.runtime_nsfw_repository import RedisRuntimeNsfwRepository
from app.repositories.postgres.video_finalization import (
    PostgresFinalResultUnitOfWork,
    PostgresVideoJobStateRepository,
)
from app.services.aggregation_service import AggregationService
from app.services.frame_extraction_service import FrameExtractionService
from app.services.queue_service import QueueService
from app.services.storage_move_service import StorageMoveService
from app.services.video_detection_service import VideoDetectionService
from app.services.video_processing_service import VideoJobProcessingError, VideoJobProcessor

logger = logging.getLogger(__name__)


class VideoQueueWorker:
    def __init__(
        self,
        *,
        settings: Settings,
        queue_service: QueueService,
        processor: VideoJobProcessor,
        consumer_name: str,
    ) -> None:
        self._settings = settings
        self._queue_service = queue_service
        self._processor = processor
        self._consumer_name = consumer_name

    async def run_forever(self) -> None:
        await self._queue_service.ensure_consumer_group()
        logger.info("video worker started", extra={"consumer_name": self._consumer_name})
        while True:
            await self.run_once()

    async def run_once(self) -> int:
        messages = await self._queue_service.read_video_job_messages(
            consumer_name=self._consumer_name,
            count=self._settings.queue_read_count,
            block_ms=self._settings.queue_block_ms,
        )
        for message in messages:
            await self._handle_message(message)
        return len(messages)

    async def _handle_message(self, message: QueuedVideoJobMessage) -> None:
        if not message.job_id:
            await self._queue_service.move_video_job_message_to_dlq(
                message,
                error_code="queue_message_missing_job_id",
                error_message="queue message did not contain a job_id",
            )
            return

        job = await self._queue_service.get_status_by_job_id(message.job_id)
        if job is None:
            await self._queue_service.move_video_job_message_to_dlq(
                message,
                error_code="queue_job_not_found",
                error_message=f"queue job {message.job_id} was not found",
            )
            return

        try:
            await self._processor.process(job)
        except VideoJobProcessingError as exc:
            if exc.failure.retryable:
                await self._queue_service.requeue_video_job(job.job_id)
                await self._queue_service.ack_video_job_message(message.message_id)
                logger.warning(
                    "video job failed retryably and was requeued",
                    extra={"job_id": job.job_id, "error_code": exc.failure.error_code},
                )
                return
            await self._queue_service.move_video_job_message_to_dlq(
                message,
                error_code=exc.failure.error_code,
                error_message=exc.failure.error_message,
            )
            logger.error(
                "video job failed terminally and was moved to dlq",
                extra={"job_id": job.job_id, "error_code": exc.failure.error_code},
            )
            return

        await self._queue_service.ack_video_job_message(message.message_id)
        logger.info("video job classified", extra={"job_id": job.job_id, "video_id": job.video_id})


async def run() -> None:
    configure_logging()
    settings = Settings()
    if not settings.is_kvrocks_configured():
        raise RuntimeError("KVROCKS_HOST is required for the video worker")
    if not settings.is_postgres_configured():
        raise RuntimeError("POSTGRES_DATABASE_URL is required for the video worker")

    redis_client = create_kvrocks_client(settings)
    postgres_engine = create_postgres_engine(settings)
    session_factory = async_sessionmaker(postgres_engine, expire_on_commit=False)
    http_client = create_http_client()

    try:
        gpu_service = build_gpu_moderation_service(settings)
        if gpu_service is None:
            raise RuntimeError("GPU moderation settings are required for the video worker")

        queue_service = QueueService(
            RedisVideoQueueRepository(redis_client, settings=settings),
            settings=settings,
        )
        detection_service = VideoDetectionService(
            settings=settings,
            storage_move_service=StorageMoveService(StorjInterfaceClient(settings, http_client)),
            unit_of_work_factory=lambda: PostgresFinalResultUnitOfWork(session_factory),
            clickhouse_buffer_repository=RedisClickHouseBufferRepository(redis_client),
            runtime_repository=RedisRuntimeNsfwRepository(redis_client, settings),
        )
        processor = VideoJobProcessor(
            settings=settings,
            queue_service=queue_service,
            job_state_repository=PostgresVideoJobStateRepository(session_factory),
            frame_extraction_service=FrameExtractionService(settings),
            gpu_service=gpu_service,
            aggregation_service=AggregationService(settings),
            detection_service=detection_service,
            http_client=http_client,
        )
        worker = VideoQueueWorker(
            settings=settings,
            queue_service=queue_service,
            processor=processor,
            consumer_name=_consumer_name(settings),
        )
        await worker.run_forever()
    finally:
        await http_client.aclose()
        await postgres_engine.dispose()
        await redis_client.aclose()


def _consumer_name(settings: Settings) -> str:
    if settings.queue_consumer_name:
        return settings.queue_consumer_name
    return f"{socket.gethostname()}-{os.getpid()}"


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
