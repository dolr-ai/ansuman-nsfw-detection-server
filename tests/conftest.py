import json
import time
from uuid import uuid4

import pytest
from pydantic import SecretStr

from app.config.settings import Settings
from app.core.security import canonical_request, sign_canonical_request


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        _env_file=None,
        service_hmac_secrets={"off-chain-agent": SecretStr("test-secret")},
        postgres_database_url="postgresql+asyncpg://user:pass@localhost/nsfw_detection",
        kvrocks_host=None,
        clickhouse_primary_database_url="clickhouse://localhost:8123/yral",
        api_base_url="http://gpu.local/v1",
        api_key=SecretStr("gpu-secret"),
        model_name="moderation-model",
    )


def signed_headers(
    *,
    method: str,
    path: str,
    body: dict[str, object] | None,
    secret: str = "test-secret",
    service: str = "off-chain-agent",
    nonce: str | None = None,
    timestamp: str | None = None,
) -> tuple[bytes, dict[str, str]]:
    raw_body = b"" if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
    resolved_timestamp = timestamp or str(int(time.time()))
    resolved_nonce = nonce or str(uuid4())
    canonical = canonical_request(
        method=method,
        path=path,
        timestamp=resolved_timestamp,
        nonce=resolved_nonce,
        raw_body=raw_body,
    )
    return raw_body, {
        "content-type": "application/json",
        "x-yral-service": service,
        "x-yral-timestamp": resolved_timestamp,
        "x-yral-nonce": resolved_nonce,
        "x-yral-signature": sign_canonical_request(secret, canonical),
    }
