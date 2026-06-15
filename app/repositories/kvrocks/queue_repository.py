import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Protocol

from redis.asyncio import Redis
from redis.asyncio.cluster import RedisCluster
from redis.exceptions import ResponseError

from app.config.settings import Settings
from app.core.constants import TERMINAL_VIDEO_STATUSES, VideoJobStatus
from app.models.video_job import VideoJob
from app.schemas.video import VideoDetectRequest


@dataclass(frozen=True)
class EnqueueResult:
    job: VideoJob
    enqueued: bool


@dataclass(frozen=True)
class QueuedVideoJobMessage:
    message_id: str
    job_id: str
    payload: dict[str, str]


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

    async def ensure_consumer_group(self) -> None:
        ...

    async def read_video_job_messages(
        self,
        *,
        consumer_name: str,
        count: int,
        block_ms: int,
    ) -> list[QueuedVideoJobMessage]:
        ...

    async def ack_video_job_message(self, message_id: str) -> None:
        ...

    async def requeue_video_job(self, job_id: str) -> None:
        ...

    async def move_video_job_message_to_dlq(
        self,
        message: QueuedVideoJobMessage,
        *,
        error_code: str,
        error_message: str,
    ) -> None:
        ...

    async def aclose(self) -> None:
        ...


class InMemoryVideoQueueRepository:
    def __init__(self) -> None:
        self._jobs: dict[str, VideoJob] = {}
        self._unique_index: dict[tuple[str, str, str], str] = {}
        self.queue: list[str] = []
        self._messages: list[QueuedVideoJobMessage] = []
        self._acked_message_ids: set[str] = set()
        self.dlq: list[dict[str, str]] = []

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
        self._messages.append(
            QueuedVideoJobMessage(
                message_id=str(len(self._messages) + 1),
                job_id=job.job_id,
                payload=_job_to_mapping(job),
            )
        )
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
        attempts = job.attempts + 1 if status == VideoJobStatus.PROCESSING else job.attempts
        updated = VideoJob(
            **{
                **asdict(job),
                "status": status,
                "attempts": attempts,
                "last_error_code": last_error_code,
                "last_error_message": last_error_message,
                "updated_at": now,
                "started_at": now if status == VideoJobStatus.PROCESSING else job.started_at,
                "finished_at": now if status in TERMINAL_VIDEO_STATUSES else job.finished_at,
            }
        )
        self._jobs[job_id] = updated
        return updated

    async def ensure_consumer_group(self) -> None:
        return None

    async def read_video_job_messages(
        self,
        *,
        consumer_name: str,
        count: int,
        block_ms: int,
    ) -> list[QueuedVideoJobMessage]:
        del consumer_name, block_ms
        return [message for message in self._messages if message.message_id not in self._acked_message_ids][:count]

    async def ack_video_job_message(self, message_id: str) -> None:
        self._acked_message_ids.add(message_id)

    async def requeue_video_job(self, job_id: str) -> None:
        job = self._jobs[job_id]
        self.queue.append(job.job_id)
        self._messages.append(
            QueuedVideoJobMessage(
                message_id=str(len(self._messages) + 1),
                job_id=job.job_id,
                payload=_job_to_mapping(job),
            )
        )

    async def move_video_job_message_to_dlq(
        self,
        message: QueuedVideoJobMessage,
        *,
        error_code: str,
        error_message: str,
    ) -> None:
        self.dlq.append(
            {
                "message_id": message.message_id,
                "job_id": message.job_id,
                "error_code": error_code,
                "error_message": error_message,
                "payload": json.dumps(message.payload, separators=(",", ":")),
            }
        )
        await self.ack_video_job_message(message.message_id)

    async def aclose(self) -> None:
        return None


class RedisVideoQueueRepository:
    def __init__(self, redis_client: Redis, settings: Settings) -> None:
        self._redis = redis_client
        self._settings = settings

    async def enqueue_video_job(self, request: VideoDetectRequest) -> EnqueueResult:
        job_key = self._job_key(request.job_id)
        existing = await self._redis.hgetall(job_key)
        if existing:
            existing_job = _job_from_mapping(existing)
            await self._redis.set(self._video_id_key(existing_job.video_id), existing_job.job_id, nx=True)
            return EnqueueResult(job=existing_job, enqueued=False)

        unique_key = self._unique_key(request.video_id, request.source_object_version, request.policy_version)
        existing_job_id = await self._redis.get(unique_key)
        if existing_job_id:
            existing = await self.get_job_by_id(existing_job_id)
            if existing is not None:
                await self._redis.set(self._video_id_key(existing.video_id), existing.job_id, nx=True)
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
        payload = _job_to_mapping(job)
        video_id_key = self._video_id_key(job.video_id)
        if isinstance(self._redis, RedisCluster):
            await self._redis.hset(job_key, mapping=payload)
            await self._redis.set(unique_key, job.job_id)
            await self._redis.set(video_id_key, job.job_id)
            await self._redis.xadd(
                self._settings.queue_stream_name,
                {"job_id": job.job_id, "payload": json.dumps(payload)},
            )
        else:
            async with self._redis.pipeline(transaction=True) as pipe:
                await pipe.hset(job_key, mapping=payload)
                await pipe.set(unique_key, job.job_id)
                await pipe.set(video_id_key, job.job_id)
                await pipe.xadd(
                    self._settings.queue_stream_name,
                    {"job_id": job.job_id, "payload": json.dumps(payload)},
                )
                await pipe.execute()
        return EnqueueResult(job=job, enqueued=True)

    async def get_job_by_video_id(self, video_id: str) -> VideoJob | None:
        job_id = await self._redis.get(self._video_id_key(video_id))
        if not job_id:
            return None
        return await self.get_job_by_id(job_id)

    async def get_job_by_id(self, job_id: str) -> VideoJob | None:
        data = await self._redis.hgetall(self._job_key(job_id))
        if not data:
            return None
        return _job_from_mapping(data)

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
        attempts = job.attempts + 1 if status == VideoJobStatus.PROCESSING else job.attempts
        updated = VideoJob(
            **{
                **asdict(job),
                "status": status,
                "attempts": attempts,
                "last_error_code": last_error_code,
                "last_error_message": last_error_message,
                "updated_at": now,
                "started_at": now if status == VideoJobStatus.PROCESSING else job.started_at,
                "finished_at": now if status in TERMINAL_VIDEO_STATUSES else job.finished_at,
            }
        )
        await self._redis.hset(self._job_key(job_id), mapping=_job_to_mapping(updated))
        return updated

    async def ensure_consumer_group(self) -> None:
        try:
            await self._redis.xgroup_create(
                self._settings.queue_stream_name,
                self._settings.queue_group_name,
                id="0",
                mkstream=True,
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def read_video_job_messages(
        self,
        *,
        consumer_name: str,
        count: int,
        block_ms: int,
    ) -> list[QueuedVideoJobMessage]:
        streams = await self._xreadgroup(consumer_name=consumer_name, count=count, block_ms=block_ms)
        messages: list[QueuedVideoJobMessage] = []
        for _, stream_messages in streams:
            for message_id, raw_payload in stream_messages:
                payload = _stream_payload_to_mapping(raw_payload)
                job_id = payload.get("job_id")
                if not job_id:
                    job_id = _json_payload(payload).get("job_id", "")
                messages.append(
                    QueuedVideoJobMessage(
                        message_id=message_id,
                        job_id=job_id,
                        payload=payload,
                    )
                )
        return messages

    async def _xreadgroup(self, *, consumer_name: str, count: int, block_ms: int):  # type: ignore[no-untyped-def]
        if not isinstance(self._redis, RedisCluster):
            return await self._redis.xreadgroup(
                self._settings.queue_group_name,
                consumer_name,
                {self._settings.queue_stream_name: ">"},
                count=count,
                block=block_ms,
            )

        stream_name = self._settings.queue_stream_name
        target_node = self._redis.get_node_from_key(stream_name)
        if target_node is None:
            raise RuntimeError(f"could not resolve Redis cluster node for stream {stream_name}")

        connection = target_node.acquire_connection()
        await target_node.disconnect_if_needed(connection)
        await connection.send_packed_command(
            connection.pack_command(
                "XREADGROUP",
                "GROUP",
                self._settings.queue_group_name,
                consumer_name,
                "COUNT",
                count,
                "BLOCK",
                block_ms,
                "STREAMS",
                stream_name,
                ">",
            )
        )
        try:
            return await connection.read_response()
        finally:
            try:
                await target_node.disconnect_if_needed(connection)
            finally:
                target_node.release(connection)

    async def ack_video_job_message(self, message_id: str) -> None:
        await self._redis.xack(
            self._settings.queue_stream_name,
            self._settings.queue_group_name,
            message_id,
        )

    async def requeue_video_job(self, job_id: str) -> None:
        job = await self.get_job_by_id(job_id)
        if job is None:
            return
        payload = _job_to_mapping(job)
        await self._redis.xadd(
            self._settings.queue_stream_name,
            {"job_id": job.job_id, "payload": json.dumps(payload, separators=(",", ":"))},
        )

    async def move_video_job_message_to_dlq(
        self,
        message: QueuedVideoJobMessage,
        *,
        error_code: str,
        error_message: str,
    ) -> None:
        await self._redis.xadd(
            self._settings.queue_dlq_stream_name,
            {
                "message_id": message.message_id,
                "job_id": message.job_id,
                "error_code": error_code,
                "error_message": error_message,
                "payload": json.dumps(message.payload, separators=(",", ":")),
            },
        )
        await self.ack_video_job_message(message.message_id)

    async def aclose(self) -> None:
        await self._redis.aclose()

    @staticmethod
    def _job_key(job_id: str) -> str:
        return f"nsfw:video_job:{job_id}"

    @staticmethod
    def _unique_key(video_id: str, source_object_version: str, policy_version: str) -> str:
        return f"nsfw:video_job_unique:{video_id}:{source_object_version}:{policy_version}"

    @staticmethod
    def _video_id_key(video_id: str) -> str:
        return f"nsfw:video_job_by_video_id:{video_id}"


def _json_payload(payload: dict[str, str]) -> dict[str, str]:
    raw_payload = payload.get("payload")
    if not raw_payload:
        return {}
    try:
        decoded = json.loads(raw_payload)
    except json.JSONDecodeError:
        return {}
    if not isinstance(decoded, dict):
        return {}
    return {str(key): str(value) for key, value in decoded.items()}


def _stream_payload_to_mapping(payload: object) -> dict[str, str]:
    if isinstance(payload, dict):
        return {str(key): str(value) for key, value in payload.items()}
    if not isinstance(payload, list | tuple):
        return {}
    return {
        str(key): str(value)
        for key, value in zip(payload[0::2], payload[1::2], strict=False)
    }


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
