import json
from typing import Protocol

from redis.asyncio import Redis


class ClickHouseBufferRepository(Protocol):
    async def push_json(self, key: str, payload: dict[str, object]) -> None:
        ...

    async def read_batch(self, key: str, limit: int) -> list[dict[str, object]]:
        ...

    async def trim_batch(self, key: str, count: int) -> None:
        ...


class InMemoryClickHouseBufferRepository:
    def __init__(self) -> None:
        self._items: dict[str, list[dict[str, object]]] = {}

    async def push_json(self, key: str, payload: dict[str, object]) -> None:
        self._items.setdefault(key, []).append(payload)

    async def read_batch(self, key: str, limit: int) -> list[dict[str, object]]:
        return list(self._items.get(key, [])[:limit])

    async def trim_batch(self, key: str, count: int) -> None:
        del self._items.setdefault(key, [])[:count]


class RedisClickHouseBufferRepository:
    def __init__(self, redis_client: Redis) -> None:
        self._redis = redis_client

    async def push_json(self, key: str, payload: dict[str, object]) -> None:
        await self._redis.rpush(key, json.dumps(payload, separators=(",", ":")))

    async def read_batch(self, key: str, limit: int) -> list[dict[str, object]]:
        raw_items = await self._redis.lrange(key, 0, limit - 1)
        return [json.loads(item) for item in raw_items]

    async def trim_batch(self, key: str, count: int) -> None:
        await self._redis.ltrim(key, count, -1)

