import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.repositories.kvrocks.queue_repository import InMemoryVideoQueueRepository
from tests.conftest import signed_headers


class FakeTextService:
    async def detect(self, text: str) -> dict[str, object]:
        return {"top_category": "safe", "should_block": False, "text_length": len(text)}


@pytest.mark.asyncio
async def test_text_endpoint_uses_stateless_service(test_settings) -> None:  # type: ignore[no-untyped-def]
    app = create_app(
        settings=test_settings,
        queue_repository=InMemoryVideoQueueRepository(),
    )
    app.state.text_detection_service = FakeTextService()
    body = {"text": "a normal dance video"}
    raw_body, headers = signed_headers(method="POST", path="/v1/text/detect", body=body)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/text/detect", content=raw_body, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"top_category": "safe", "should_block": False, "text_length": 20}

