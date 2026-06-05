import time
from typing import Protocol

from redis.asyncio import Redis


class AuthNonceRepository(Protocol):
    async def store_nonce_once(self, service_name: str, nonce: str, ttl_seconds: int) -> bool:
        """Return True when nonce was stored, False when it was already seen."""


class InMemoryAuthNonceRepository:
    def __init__(self) -> None:
        self._nonces: dict[tuple[str, str], float] = {}

    async def store_nonce_once(self, service_name: str, nonce: str, ttl_seconds: int) -> bool:
        now = time.time()
        expired = [key for key, expires_at in self._nonces.items() if expires_at <= now]
        for key in expired:
            self._nonces.pop(key, None)

        key = (service_name, nonce)
        if key in self._nonces:
            return False
        self._nonces[key] = now + ttl_seconds
        return True


class RedisAuthNonceRepository:
    def __init__(self, redis_client: Redis) -> None:
        self._redis = redis_client

    async def store_nonce_once(self, service_name: str, nonce: str, ttl_seconds: int) -> bool:
        key = f"nsfw:auth_nonce:{service_name}:{nonce}"
        return bool(await self._redis.set(key, "1", ex=ttl_seconds, nx=True))

