import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.repositories.kvrocks.auth_nonce_repository import InMemoryAuthNonceRepository
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
async def test_signed_video_detect_enqueues_once(test_settings) -> None:  # type: ignore[no-untyped-def]
    queue_repository = InMemoryVideoQueueRepository()
    app = create_app(
        settings=test_settings,
        nonce_repository=InMemoryAuthNonceRepository(),
        queue_repository=queue_repository,
    )
    body = video_body()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        raw_body, headers = signed_headers(method="POST", path="/v1/videos/detect", body=body, nonce="nonce-1")
        response = await client.post("/v1/videos/detect", content=raw_body, headers=headers)

        raw_body, headers = signed_headers(method="POST", path="/v1/videos/detect", body=body, nonce="nonce-2")
        repeat_response = await client.post("/v1/videos/detect", content=raw_body, headers=headers)

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert repeat_response.status_code == 202
    assert len(queue_repository.queue) == 1


@pytest.mark.asyncio
async def test_replayed_nonce_rejected(test_settings) -> None:  # type: ignore[no-untyped-def]
    app = create_app(
        settings=test_settings,
        nonce_repository=InMemoryAuthNonceRepository(),
        queue_repository=InMemoryVideoQueueRepository(),
    )
    body = video_body()
    raw_body, headers = signed_headers(method="POST", path="/v1/videos/detect", body=body, nonce="same-nonce")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post("/v1/videos/detect", content=raw_body, headers=headers)
        second = await client.post("/v1/videos/detect", content=raw_body, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 401
    assert second.json()["error"]["code"] == "auth_replayed_nonce"


@pytest.mark.asyncio
async def test_status_endpoint_returns_queued_status(test_settings) -> None:  # type: ignore[no-untyped-def]
    queue_repository = InMemoryVideoQueueRepository()
    app = create_app(
        settings=test_settings,
        nonce_repository=InMemoryAuthNonceRepository(),
        queue_repository=queue_repository,
    )
    body = video_body()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        raw_body, headers = signed_headers(method="POST", path="/v1/videos/detect", body=body, nonce="nonce-1")
        await client.post("/v1/videos/detect", content=raw_body, headers=headers)

        raw_body, headers = signed_headers(method="GET", path="/v1/videos/video-1/status", body=None, nonce="nonce-2")
        response = await client.request("GET", "/v1/videos/video-1/status", content=raw_body, headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "queued"
