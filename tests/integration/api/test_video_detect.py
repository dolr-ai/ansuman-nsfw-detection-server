import time

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.repositories.kvrocks.queue_repository import InMemoryVideoQueueRepository
from tests.conftest import signed_headers


def video_body() -> dict[str, object]:
    return {
        "job_id": "nsfw:video-1:nsfw_policy_v1:",
        "video_id": "video-1",
        "publisher_user_id": "user-1",
        "source_video_uri": "https://example.com/video.mp4",
        "post_id": None,
        "canister_id": None,
        "source_object_version": "",
        "upload_event_id": None,
        "policy_version": "nsfw_policy_v1",
        "trace_id": "trace-1",
    }


@pytest.mark.asyncio
async def test_signed_video_detect_is_idempotent_by_job_id(test_settings) -> None:  # type: ignore[no-untyped-def]
    queue_repository = InMemoryVideoQueueRepository()
    app = create_app(
        settings=test_settings,
        queue_repository=queue_repository,
    )
    body = video_body()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        raw_body, headers = signed_headers(method="POST", path="/v1/videos/detect", body=body)
        response = await client.post("/v1/videos/detect", content=raw_body, headers=headers)

        raw_body, headers = signed_headers(method="POST", path="/v1/videos/detect", body=body)
        repeat_response = await client.post("/v1/videos/detect", content=raw_body, headers=headers)

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert repeat_response.status_code == 202
    assert len(queue_repository.queue) == 1


@pytest.mark.asyncio
async def test_stale_timestamp_rejected(test_settings) -> None:  # type: ignore[no-untyped-def]
    app = create_app(
        settings=test_settings,
        queue_repository=InMemoryVideoQueueRepository(),
    )
    body = video_body()
    raw_body, headers = signed_headers(
        method="POST",
        path="/v1/videos/detect",
        body=body,
        timestamp=str(int(time.time()) - 10_000),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/videos/detect", content=raw_body, headers=headers)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_timestamp_out_of_range"


@pytest.mark.asyncio
async def test_missing_internal_auth_header_returns_401(test_settings) -> None:  # type: ignore[no-untyped-def]
    app = create_app(
        settings=test_settings,
        queue_repository=InMemoryVideoQueueRepository(),
    )
    body = video_body()
    raw_body, headers = signed_headers(method="POST", path="/v1/videos/detect", body=body)
    headers.pop("x-internal-signature")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/videos/detect", content=raw_body, headers=headers)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_missing_headers"


@pytest.mark.asyncio
async def test_status_endpoint_returns_queued_status(test_settings) -> None:  # type: ignore[no-untyped-def]
    queue_repository = InMemoryVideoQueueRepository()
    app = create_app(
        settings=test_settings,
        queue_repository=queue_repository,
    )
    body = video_body()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        raw_body, headers = signed_headers(method="POST", path="/v1/videos/detect", body=body)
        await client.post("/v1/videos/detect", content=raw_body, headers=headers)

        raw_body, headers = signed_headers(method="GET", path="/v1/videos/video-1/status", body=None)
        response = await client.request("GET", "/v1/videos/video-1/status", content=raw_body, headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "queued"


def test_openapi_marks_internal_auth_headers_required(test_settings) -> None:  # type: ignore[no-untyped-def]
    app = create_app(
        settings=test_settings,
        queue_repository=InMemoryVideoQueueRepository(),
    )

    parameters = app.openapi()["paths"]["/v1/videos/detect"]["post"]["parameters"]
    by_name = {parameter["name"]: parameter for parameter in parameters}

    assert by_name["X-Internal-Timestamp"]["required"] is True
    assert by_name["X-Internal-Signature"]["required"] is True
