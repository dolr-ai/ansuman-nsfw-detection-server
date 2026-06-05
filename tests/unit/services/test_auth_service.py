import time

import pytest

from app.errors.base import AppError
from app.services.auth_service import AuthService
from tests.conftest import signed_headers


@pytest.mark.asyncio
async def test_valid_signature_is_accepted(test_settings) -> None:  # type: ignore[no-untyped-def]
    body = {"hello": "world"}
    raw_body, headers = signed_headers(method="POST", path="/v1/videos/detect", body=body)
    service = AuthService(test_settings)

    context = await service.authenticate(
        method="POST",
        path="/v1/videos/detect",
        headers=headers,
        raw_body=raw_body,
    )

    assert context.timestamp == int(headers["x-internal-timestamp"])


@pytest.mark.asyncio
async def test_missing_auth_header_is_rejected(test_settings) -> None:  # type: ignore[no-untyped-def]
    body = {"hello": "world"}
    raw_body, headers = signed_headers(method="POST", path="/v1/videos/detect", body=body)
    headers.pop("x-internal-signature")
    service = AuthService(test_settings)

    with pytest.raises(AppError) as exc:
        await service.authenticate(method="POST", path="/v1/videos/detect", headers=headers, raw_body=raw_body)

    assert exc.value.code == "auth_missing_headers"


@pytest.mark.asyncio
async def test_bad_timestamp_is_rejected(test_settings) -> None:  # type: ignore[no-untyped-def]
    body = {"hello": "world"}
    raw_body, headers = signed_headers(
        method="POST",
        path="/v1/videos/detect",
        body=body,
        timestamp="not-a-timestamp",
    )
    service = AuthService(test_settings)

    with pytest.raises(AppError) as exc:
        await service.authenticate(method="POST", path="/v1/videos/detect", headers=headers, raw_body=raw_body)

    assert exc.value.code == "auth_bad_timestamp"


@pytest.mark.asyncio
async def test_expired_timestamp_is_rejected(test_settings) -> None:  # type: ignore[no-untyped-def]
    body = {"hello": "world"}
    raw_body, headers = signed_headers(
        method="POST",
        path="/v1/videos/detect",
        body=body,
        timestamp=str(int(time.time()) - 10_000),
    )
    service = AuthService(test_settings)

    with pytest.raises(AppError) as exc:
        await service.authenticate(method="POST", path="/v1/videos/detect", headers=headers, raw_body=raw_body)

    assert exc.value.code == "auth_timestamp_out_of_range"


@pytest.mark.asyncio
async def test_future_timestamp_is_rejected(test_settings) -> None:  # type: ignore[no-untyped-def]
    body = {"hello": "world"}
    raw_body, headers = signed_headers(
        method="POST",
        path="/v1/videos/detect",
        body=body,
        timestamp=str(int(time.time()) + 10_000),
    )
    service = AuthService(test_settings)

    with pytest.raises(AppError) as exc:
        await service.authenticate(method="POST", path="/v1/videos/detect", headers=headers, raw_body=raw_body)

    assert exc.value.code == "auth_timestamp_out_of_range"


@pytest.mark.asyncio
async def test_bad_signature_is_rejected(test_settings) -> None:  # type: ignore[no-untyped-def]
    body = {"hello": "world"}
    raw_body, headers = signed_headers(method="POST", path="/v1/videos/detect", body=body)
    headers["x-internal-signature"] = "bad"
    service = AuthService(test_settings)

    with pytest.raises(AppError) as exc:
        await service.authenticate(method="POST", path="/v1/videos/detect", headers=headers, raw_body=raw_body)

    assert exc.value.code == "auth_bad_signature"


@pytest.mark.asyncio
async def test_missing_secret_returns_bad_signature(test_settings) -> None:  # type: ignore[no-untyped-def]
    test_settings.internal_request_hmac_secret = None
    body = {"hello": "world"}
    raw_body, headers = signed_headers(method="POST", path="/v1/videos/detect", body=body)
    service = AuthService(test_settings)

    with pytest.raises(AppError) as exc:
        await service.authenticate(method="POST", path="/v1/videos/detect", headers=headers, raw_body=raw_body)

    assert exc.value.code == "auth_bad_signature"
    assert exc.value.status_code == 401
