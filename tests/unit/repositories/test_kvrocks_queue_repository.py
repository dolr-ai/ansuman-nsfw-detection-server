import pytest

from app.config.settings import Settings
from app.repositories.kvrocks.queue_repository import RedisVideoQueueRepository
from app.schemas.video import VideoDetectRequest


def request(
    *,
    job_id: str = "job-1",
    video_id: str = "video-1",
    source_object_version: str = "source-v1",
) -> VideoDetectRequest:
    return VideoDetectRequest(
        job_id=job_id,
        video_id=video_id,
        publisher_user_id="user-1",
        source_video_uri="https://example.com/video.mp4",
        source_object_version=source_object_version,
        policy_version="nsfw_policy_v1",
        trace_id="trace-1",
    )


class FakePipeline:
    def __init__(self, redis: "FakeRedis") -> None:
        self._redis = redis

    async def __aenter__(self) -> "FakePipeline":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def hset(self, key: str, *, mapping: dict[str, str]) -> None:
        await self._redis.hset(key, mapping=mapping)

    async def set(self, key: str, value: str) -> None:
        await self._redis.set(key, value)

    async def xadd(self, stream: str, payload: dict[str, str]) -> None:
        await self._redis.xadd(stream, payload)

    async def execute(self) -> None:
        return None


class FakeRedis:
    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, str]] = {}
        self.values: dict[str, str] = {}
        self.stream_entries: list[tuple[str, dict[str, str]]] = []
        self.scan_called = False

    async def hgetall(self, key: str) -> dict[str, str]:
        return self.hashes.get(key, {})

    async def hset(self, key: str, *, mapping: dict[str, str]) -> None:
        self.hashes[key] = dict(mapping)

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, *, nx: bool = False) -> bool:
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def xadd(self, stream: str, payload: dict[str, str]) -> None:
        self.stream_entries.append((stream, payload))

    def pipeline(self, *, transaction: bool) -> FakePipeline:
        assert transaction is True
        return FakePipeline(self)

    async def scan_iter(self, _: str):  # type: ignore[no-untyped-def]
        self.scan_called = True
        raise AssertionError("status lookup should not scan job keys")
        yield

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_enqueue_writes_video_id_index_for_status_lookup() -> None:
    redis = FakeRedis()
    repository = RedisVideoQueueRepository(redis, settings=Settings(_env_file=None))  # type: ignore[arg-type]

    result = await repository.enqueue_video_job(request())
    job = await repository.get_job_by_video_id("video-1")

    assert result.enqueued is True
    assert redis.values["nsfw:video_job_by_video_id:video-1"] == "job-1"
    assert job is not None
    assert job.job_id == "job-1"
    assert redis.scan_called is False


@pytest.mark.asyncio
async def test_get_job_by_video_id_uses_direct_index() -> None:
    redis = FakeRedis()
    repository = RedisVideoQueueRepository(redis, settings=Settings(_env_file=None))  # type: ignore[arg-type]
    await repository.enqueue_video_job(request(job_id="job-1", video_id="video-1", source_object_version="source-v1"))
    await repository.enqueue_video_job(request(job_id="job-2", video_id="video-1", source_object_version="source-v2"))

    job = await repository.get_job_by_video_id("video-1")

    assert job is not None
    assert job.job_id == "job-2"
    assert redis.scan_called is False
