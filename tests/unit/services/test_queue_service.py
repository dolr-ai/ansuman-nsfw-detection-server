import pytest
from redis.exceptions import MaxConnectionsError

from app.config.settings import Settings
from app.services.queue_service import QueueService


class PoolExhaustedThenAvailableRepository:
    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    async def get_job_by_video_id(self, video_id: str):  # type: ignore[no-untyped-def]
        self.calls += 1
        if self.calls <= self.failures:
            raise MaxConnectionsError("Too many connections")
        return None


def retry_settings(*, max_attempts: int) -> Settings:
    return Settings(
        _env_file=None,
        KVROCKS_POOL_MAX_ATTEMPTS=max_attempts,
        KVROCKS_POOL_RETRY_BASE_DELAY_SECONDS=0,
    )


@pytest.mark.asyncio
async def test_status_read_retries_transient_pool_exhaustion() -> None:
    repository = PoolExhaustedThenAvailableRepository(failures=2)
    service = QueueService(repository, settings=retry_settings(max_attempts=3))  # type: ignore[arg-type]

    result = await service.get_status_by_video_id("video-1")

    assert result is None
    assert repository.calls == 3


@pytest.mark.asyncio
async def test_status_read_raises_after_pool_retry_limit() -> None:
    repository = PoolExhaustedThenAvailableRepository(failures=3)
    service = QueueService(repository, settings=retry_settings(max_attempts=2))  # type: ignore[arg-type]

    with pytest.raises(MaxConnectionsError):
        await service.get_status_by_video_id("video-1")

    assert repository.calls == 2
