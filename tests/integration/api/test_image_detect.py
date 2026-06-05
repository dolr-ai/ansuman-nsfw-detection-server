import base64

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.repositories.kvrocks.queue_repository import InMemoryVideoQueueRepository
from tests.conftest import signed_headers


class FakeImageService:
    async def detect_base64(self, image_base64: str) -> dict[str, object]:
        return {"top_category": "safe", "bytes": len(base64.b64decode(image_base64))}

    async def detect_url(self, image_url: str) -> dict[str, object]:
        return {"top_category": "safe", "url": image_url}


@pytest.mark.asyncio
async def test_image_base64_endpoint_uses_stateless_service(test_settings) -> None:  # type: ignore[no-untyped-def]
    app = create_app(
        settings=test_settings,
        queue_repository=InMemoryVideoQueueRepository(),
    )
    app.state.image_detection_service = FakeImageService()
    body = {"image_base64": base64.b64encode(b"image").decode("ascii")}
    raw_body, headers = signed_headers(method="POST", path="/v1/images/detect-base64", body=body)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/images/detect-base64", content=raw_body, headers=headers)

    assert response.status_code == 200
    assert response.json() == {"top_category": "safe", "bytes": 5}

