import json
import time

import pytest
from pydantic import SecretStr

from app.config.settings import Settings
from app.core.security import sign_request


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        _env_file=None,
        internal_request_hmac_secret=SecretStr("test-secret"),
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
    timestamp: str | None = None,
) -> tuple[bytes, dict[str, str]]:
    raw_body = b"" if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
    resolved_timestamp = timestamp or str(int(time.time()))
    return raw_body, {
        "content-type": "application/json",
        "x-internal-timestamp": resolved_timestamp,
        "x-internal-signature": sign_request(
            secret,
            timestamp=resolved_timestamp,
            method=method,
            path=path,
            body=raw_body,
        ),
    }
