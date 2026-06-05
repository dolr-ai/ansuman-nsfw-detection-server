import json
from typing import Protocol

from redis.asyncio import Redis

from app.config.settings import Settings


class RuntimeNsfwRepository(Protocol):
    async def write_result(self, video_id: str, payload: dict[str, object]) -> None:
        ...


class InMemoryRuntimeNsfwRepository:
    def __init__(self) -> None:
        self.items: dict[str, dict[str, object]] = {}

    async def write_result(self, video_id: str, payload: dict[str, object]) -> None:
        self.items[video_id] = payload


class RedisRuntimeNsfwRepository:
    def __init__(self, redis_client: Redis, settings: Settings) -> None:
        self._redis = redis_client
        self._settings = settings

    async def write_result(self, video_id: str, payload: dict[str, object]) -> None:
        key = f"{self._settings.runtime_nsfw_key_prefix}{video_id}"
        await self._redis.set(key, json.dumps(payload, separators=(",", ":")))

