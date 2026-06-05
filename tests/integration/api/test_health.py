import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.repositories.kvrocks.queue_repository import InMemoryVideoQueueRepository


class ReadyService:
    async def check(self) -> list[dict[str, object]]:
        return [
            {"name": "postgres", "ready": True, "detail": "fake"},
            {"name": "kvrocks", "ready": True, "detail": "fake"},
            {"name": "clickhouse", "ready": True, "detail": "fake"},
            {"name": "gpu", "ready": True, "detail": "fake"},
            {"name": "ffmpeg", "ready": True, "detail": "fake"},
            {"name": "ffprobe", "ready": True, "detail": "fake"},
        ]


@pytest.mark.asyncio
async def test_health_and_ready(test_settings) -> None:  # type: ignore[no-untyped-def]
    app = create_app(
        settings=test_settings,
        queue_repository=InMemoryVideoQueueRepository(),
    )
    app.state.readiness_service = ReadyService()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        health_response = await client.get("/health")
        ready_response = await client.get("/ready")

    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}
    assert ready_response.status_code == 200
    assert ready_response.json()["status"] == "ready"

