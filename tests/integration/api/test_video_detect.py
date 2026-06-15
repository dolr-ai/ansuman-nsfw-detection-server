import time
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from redis.exceptions import MaxConnectionsError

from app.core.constants import VideoJobStatus
from app.main import create_app
from app.models.video_result import VideoModerationResult
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


def final_result() -> VideoModerationResult:
    now = datetime.now(UTC)
    return VideoModerationResult(
        job_id="nsfw:video-1:nsfw_policy_v1:",
        video_id="video-1",
        policy_version="nsfw_policy_v1",
        prompt_version="visual_batch_moderation_v1",
        aggregation_version="hard_any_frame_v1",
        final_is_nsfw=True,
        final_score=0.8,
        final_top_category="porn",
        max_overall_severity=4,
        nsfw_frame_count=1,
        total_frame_count=5,
        move_required=True,
        move_threshold=0.8,
        max_category_severities={"porn": 4},
        legacy_nsfw_ec="explicit",
        legacy_nsfw_gore="VERY_UNLIKELY",
        final_response={"final_is_nsfw": True},
        created_at=now,
        updated_at=now,
    )


class FakeResultReader:
    async def get_by_job_id(self, job_id: str) -> VideoModerationResult | None:
        assert job_id == "nsfw:video-1:nsfw_policy_v1:"
        return final_result()

    async def get_latest_by_video_id(self, video_id: str) -> VideoModerationResult | None:
        assert video_id == "video-1"
        return final_result()


class ExhaustedQueueRepository:
    async def enqueue_video_job(self, request):  # type: ignore[no-untyped-def]
        raise MaxConnectionsError("Too many connections")

    async def get_job_by_video_id(self, video_id: str):  # type: ignore[no-untyped-def]
        raise MaxConnectionsError("Too many connections")

    async def aclose(self) -> None:
        return None


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


@pytest.mark.asyncio
async def test_video_detect_returns_503_when_queue_pool_is_exhausted(test_settings) -> None:  # type: ignore[no-untyped-def]
    app = create_app(
        settings=test_settings,
        queue_repository=ExhaustedQueueRepository(),
    )
    body = video_body()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        raw_body, headers = signed_headers(method="POST", path="/v1/videos/detect", body=body)
        response = await client.post("/v1/videos/detect", content=raw_body, headers=headers)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "queue_unavailable"


@pytest.mark.asyncio
async def test_status_endpoint_returns_503_when_queue_pool_is_exhausted(test_settings) -> None:  # type: ignore[no-untyped-def]
    app = create_app(
        settings=test_settings,
        queue_repository=ExhaustedQueueRepository(),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        raw_body, headers = signed_headers(method="GET", path="/v1/videos/video-1/status", body=None)
        response = await client.request("GET", "/v1/videos/video-1/status", content=raw_body, headers=headers)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "queue_unavailable"


@pytest.mark.asyncio
async def test_status_endpoint_returns_final_result_for_classified_video(test_settings) -> None:  # type: ignore[no-untyped-def]
    queue_repository = InMemoryVideoQueueRepository()
    app = create_app(
        settings=test_settings,
        queue_repository=queue_repository,
        video_result_reader=FakeResultReader(),
    )
    body = video_body()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        raw_body, headers = signed_headers(method="POST", path="/v1/videos/detect", body=body)
        await client.post("/v1/videos/detect", content=raw_body, headers=headers)
        await queue_repository.update_status("nsfw:video-1:nsfw_policy_v1:", VideoJobStatus.CLASSIFIED)

        raw_body, headers = signed_headers(method="GET", path="/v1/videos/video-1/status", body=None)
        response = await client.request("GET", "/v1/videos/video-1/status", content=raw_body, headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "classified"
    assert response.json()["final_result"]["final_score"] == 0.8
    assert response.json()["final_result"]["max_category_severities"] == {"porn": 4}


def test_openapi_marks_internal_auth_headers_required(test_settings) -> None:  # type: ignore[no-untyped-def]
    app = create_app(
        settings=test_settings,
        queue_repository=InMemoryVideoQueueRepository(),
    )

    parameters = app.openapi()["paths"]["/v1/videos/detect"]["post"]["parameters"]
    by_name = {parameter["name"]: parameter for parameter in parameters}

    assert by_name["X-Internal-Timestamp"]["required"] is True
    assert by_name["X-Internal-Signature"]["required"] is True
