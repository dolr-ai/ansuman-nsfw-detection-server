import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Protocol

from redis.asyncio import Redis

from app.config.settings import Settings
from app.core.constants import TERMINAL_VIDEO_STATUSES, VideoJobStatus
from app.models.video_job import VideoJob
from app.schemas.video import VideoDetectRequest


@dataclass(frozen=True)
class EnqueueResult:
    job: VideoJob
    enqueued: bool


class VideoQueueRepository(Protocol):
    async def enqueue_video_job(self, request: VideoDetectRequest) -> EnqueueResult:
        ...

    async def get_job_by_video_id(self, video_id: str) -> VideoJob | None:
        ...

    async def get_job_by_id(self, job_id: str) -> VideoJob | None:
        ...

    async def update_status(
        self,
        job_id: str,
        status: VideoJobStatus,
        *,
        last_error_code: str | None = None,
        last_error_message: str | None = None,
    ) -> VideoJob | None:
        ...


class InMemoryVideoQueueRepository:
    def __init__(self) -> None:
        self._jobs: dict[str, VideoJob] = {}
        self._unique_index: dict[tuple[str, str, str], str] = {}
        self.queue: list[str] = []

    async def enqueue_video_job(self, request: VideoDetectRequest) -> EnqueueResult:
        existing_job = self._jobs.get(request.job_id)
        if existing_job is not None:
            return EnqueueResult(job=existing_job, enqueued=False)

        unique_key = (request.video_id, request.source_object_version, request.policy_version)
        existing_job_id = self._unique_index.get(unique_key)
        if existing_job_id is not None:
            existing = self._jobs[existing_job_id]
            if existing.status in TERMINAL_VIDEO_STATUSES or existing.status in {
                VideoJobStatus.QUEUED,
                VideoJobStatus.PROCESSING,
                VideoJobStatus.CLASSIFIED,
            }:
                return EnqueueResult(job=existing, enqueued=False)

        now = datetime.now(UTC)
        job = VideoJob(
            job_id=request.job_id,
            video_id=request.video_id,
            source_object_version=request.source_object_version,
            policy_version=request.policy_version,
            status=VideoJobStatus.QUEUED,
            publisher_user_id=request.publisher_user_id,
            post_id=request.post_id,
            canister_id=request.canister_id,
            source_video_uri=request.source_video_uri,
            upload_event_id=request.upload_event_id,
            trace_id=request.trace_id,
            created_at=now,
            updated_at=now,
        )
        self._jobs[job.job_id] = job
        self._unique_index[unique_key] = job.job_id
        self.queue.append(job.job_id)
        return EnqueueResult(job=job, enqueued=True)

    async def get_job_by_video_id(self, video_id: str) -> VideoJob | None:
        matches = [job for job in self._jobs.values() if job.video_id == video_id]
        if not matches:
            return None
        return max(matches, key=lambda job: job.updated_at or datetime.min.replace(tzinfo=UTC))

    async def get_job_by_id(self, job_id: str) -> VideoJob | None:
        return self._jobs.get(job_id)

    async def update_status(
        self,
        job_id: str,
        status: VideoJobStatus,
        *,
        last_error_code: str | None = None,
        last_error_message: str | None = None,
    ) -> VideoJob | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        now = datetime.now(UTC)
        updated = VideoJob(
            **{
                **asdict(job),
                "status": status,
                "last_error_code": last_error_code,
                "last_error_message": last_error_message,
                "updated_at": now,
                "finished_at": now if status in TERMINAL_VIDEO_STATUSES else job.finished_at,
            }
        )
        self._jobs[job_id] = updated
        return updated


class RedisVideoQueueRepository:
    def __init__(self, redis_client: Redis, settings: Settings) -> None:
        self._redis = redis_client
        self._settings = settings

    async def enqueue_video_job(self, request: VideoDetectRequest) -> EnqueueResult:
        job_key = self._job_key(request.job_id)
        existing = await self._redis.hgetall(job_key)
        if existing:
            return EnqueueResult(job=self._job_from_mapping(existing), enqueued=False)

        unique_key = self._unique_key(request.video_id, request.source_object_version, request.policy_version)
        existing_job_id = await self._redis.get(unique_key)
        if existing_job_id:
            existing = await self.get_job_by_id(existing_job_id)
            if existing is not None:
                return EnqueueResult(job=existing, enqueued=False)

        now = datetime.now(UTC)
        job = VideoJob(
            job_id=request.job_id,
            video_id=request.video_id,
            source_object_version=request.source_object_version,
            policy_version=request.policy_version,
            status=VideoJobStatus.QUEUED,
            publisher_user_id=request.publisher_user_id,
            post_id=request.post_id,
            canister_id=request.canister_id,
            source_video_uri=request.source_video_uri,
            upload_event_id=request.upload_event_id,
            trace_id=request.trace_id,
            created_at=now,
            updated_at=now,
        )
        payload = self._job_to_mapping(job)
        async with self._redis.pipeline(transaction=True) as pipe:
            await pipe.hset(job_key, mapping=payload)
            await pipe.set(unique_key, job.job_id)
            await pipe.xadd(self._settings.queue_stream_name, {"job_id": job.job_id, "payload": json.dumps(payload)})
            await pipe.execute()
        return EnqueueResult(job=job, enqueued=True)

    async def get_job_by_video_id(self, video_id: str) -> VideoJob | None:
        # Runtime status lookup by video_id is primarily served from PostgreSQL once Phase 3 lands.
        # For queue-only Phase 2, scan the stream-backed job keys conservatively.
        async for key in self._redis.scan_iter("nsfw:video_job:*"):
            data = await self._redis.hgetall(key)
            if data.get("video_id") == video_id:
                return self._job_from_mapping(data)
        return None

    async def get_job_by_id(self, job_id: str) -> VideoJob | None:
        data = await self._redis.hgetall(self._job_key(job_id))
        if not data:
            return None
        return self._job_from_mapping(data)

    async def update_status(
        self,
        job_id: str,
        status: VideoJobStatus,
        *,
        last_error_code: str | None = None,
        last_error_message: str | None = None,
    ) -> VideoJob | None:
        job = await self.get_job_by_id(job_id)
        if job is None:
            return None
        now = datetime.now(UTC)
        updated = VideoJob(
            **{
                **asdict(job),
                "status": status,
                "last_error_code": last_error_code,
                "last_error_message": last_error_message,
                "updated_at": now,
                "finished_at": now if status in TERMINAL_VIDEO_STATUSES else job.finished_at,
            }
        )
        await self._redis.hset(self._job_key(job_id), mapping=self._job_to_mapping(updated))
        return updated

    @staticmethod
    def _job_key(job_id: str) -> str:
        return f"nsfw:video_job:{job_id}"

    @staticmethod
    def _unique_key(video_id: str, source_object_version: str, policy_version: str) -> str:
        return f"nsfw:video_job_unique:{video_id}:{source_object_version}:{policy_version}"

    @staticmethod
    def _job_to_mapping(job: VideoJob) -> dict[str, str]:
        data = asdict(job)
        data["status"] = job.status.value
        for key, value in list(data.items()):
            if isinstance(value, datetime):
                data[key] = value.isoformat()
            elif value is None:
                data[key] = ""
            else:
                data[key] = str(value)
        return data

    @staticmethod
    def _job_from_mapping(data: dict[str, str]) -> VideoJob:
        def optional(value: str | None) -> str | None:
            return value or None

        def optional_datetime(value: str | None) -> datetime | None:
            if not value:
                return None
            return datetime.fromisoformat(value)

        return VideoJob(
            job_id=data["job_id"],
            video_id=data["video_id"],
            source_object_version=data.get("source_object_version", ""),
            policy_version=data["policy_version"],
            status=VideoJobStatus(data["status"]),
            publisher_user_id=data["publisher_user_id"],
            post_id=optional(data.get("post_id")),
            canister_id=optional(data.get("canister_id")),
            source_video_uri=data["source_video_uri"],
            upload_event_id=optional(data.get("upload_event_id")),
            trace_id=optional(data.get("trace_id")),
            attempts=int(data.get("attempts", "0") or "0"),
            last_error_code=optional(data.get("last_error_code")),
            last_error_message=optional(data.get("last_error_message")),
            created_at=optional_datetime(data.get("created_at")),
            updated_at=optional_datetime(data.get("updated_at")),
            started_at=optional_datetime(data.get("started_at")),
            finished_at=optional_datetime(data.get("finished_at")),
        )

