import time

import pytest

from app.errors.base import AppError
from app.repositories.kvrocks.auth_nonce_repository import InMemoryAuthNonceRepository
from app.services.auth_service import AuthService
from tests.conftest import signed_headers


@pytest.mark.asyncio
async def test_valid_signature_is_accepted(test_settings) -> None:  # type: ignore[no-untyped-def]
    body = {"hello": "world"}
    raw_body, headers = signed_headers(method="POST", path="/v1/videos/detect", body=body)
    service = AuthService(test_settings, InMemoryAuthNonceRepository())

    context = await service.authenticate(
        method="POST",
        path="/v1/videos/detect",
        headers=headers,
        raw_body=raw_body,
    )

    assert context.service_name == "off-chain-agent"


@pytest.mark.asyncio
async def test_replayed_nonce_is_rejected(test_settings) -> None:  # type: ignore[no-untyped-def]
    body = {"hello": "world"}
    raw_body, headers = signed_headers(method="POST", path="/v1/videos/detect", body=body, nonce="same")
    service = AuthService(test_settings, InMemoryAuthNonceRepository())

    await service.authenticate(method="POST", path="/v1/videos/detect", headers=headers, raw_body=raw_body)

    with pytest.raises(AppError) as exc:
        await service.authenticate(method="POST", path="/v1/videos/detect", headers=headers, raw_body=raw_body)

    assert exc.value.code == "auth_replayed_nonce"


@pytest.mark.asyncio
async def test_expired_timestamp_is_rejected(test_settings) -> None:  # type: ignore[no-untyped-def]
    body = {"hello": "world"}
    raw_body, headers = signed_headers(
        method="POST",
        path="/v1/videos/detect",
        body=body,
        timestamp=str(int(time.time()) - 10_000),
    )
    service = AuthService(test_settings, InMemoryAuthNonceRepository())

    with pytest.raises(AppError) as exc:
        await service.authenticate(method="POST", path="/v1/videos/detect", headers=headers, raw_body=raw_body)

    assert exc.value.code == "auth_timestamp_out_of_range"


@pytest.mark.asyncio
async def test_bad_signature_is_rejected(test_settings) -> None:  # type: ignore[no-untyped-def]
    body = {"hello": "world"}
    raw_body, headers = signed_headers(method="POST", path="/v1/videos/detect", body=body)
    headers["x-yral-signature"] = "bad"
    service = AuthService(test_settings, InMemoryAuthNonceRepository())

    with pytest.raises(AppError) as exc:
        await service.authenticate(method="POST", path="/v1/videos/detect", headers=headers, raw_body=raw_body)

    assert exc.value.code == "auth_bad_signature"

