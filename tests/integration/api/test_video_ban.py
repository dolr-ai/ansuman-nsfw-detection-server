import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.repositories.kvrocks.queue_repository import InMemoryVideoQueueRepository
from app.services.manual_ban_service import ManualBanResult
from tests.conftest import signed_headers


def ban_body() -> dict[str, object]:
    return {
        "publisher_user_id": "user-1",
        "post_id": "post-1",
        "canister_id": "canister-1",
        "reason": "user_report_approved",
        "source": "google_chat",
        "moderator_id": None,
        "trace_id": "trace-1",
    }


class FakeManualBanService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def ban_video(self, video_id, request):  # type: ignore[no-untyped-def]
        self.calls.append((video_id, request))
        return ManualBanResult(
            video_id=video_id,
            status="banned",
            excluded_videos_written=True,
            legacy_nsfw_agg_written=True,
            trace_id=request.trace_id,
        )


@pytest.mark.asyncio
async def test_signed_video_ban_records_manual_ban(test_settings) -> None:  # type: ignore[no-untyped-def]
    manual_ban_service = FakeManualBanService()
    app = create_app(
        settings=test_settings,
        queue_repository=InMemoryVideoQueueRepository(),
        manual_ban_service=manual_ban_service,
    )
    body = ban_body()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        raw_body, headers = signed_headers(method="POST", path="/v1/videos/video-1/ban", body=body)
        response = await client.post("/v1/videos/video-1/ban", content=raw_body, headers=headers)

    assert response.status_code == 200
    assert response.json() == {
        "video_id": "video-1",
        "status": "banned",
        "excluded_videos_written": True,
        "legacy_nsfw_agg_written": True,
        "trace_id": "trace-1",
    }
    assert len(manual_ban_service.calls) == 1
    video_id, request = manual_ban_service.calls[0]
    assert video_id == "video-1"
    assert request.publisher_user_id == "user-1"
    assert request.post_id == "post-1"
    assert request.canister_id == "canister-1"


@pytest.mark.asyncio
async def test_video_ban_rejects_bad_signature(test_settings) -> None:  # type: ignore[no-untyped-def]
    app = create_app(
        settings=test_settings,
        queue_repository=InMemoryVideoQueueRepository(),
        manual_ban_service=FakeManualBanService(),
    )
    body = ban_body()
    raw_body, headers = signed_headers(method="POST", path="/v1/videos/video-1/ban", body=body)
    headers["x-internal-signature"] = "bad"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/videos/video-1/ban", content=raw_body, headers=headers)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "auth_bad_signature"
