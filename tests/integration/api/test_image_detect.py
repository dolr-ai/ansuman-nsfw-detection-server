import base64

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.repositories.kvrocks.queue_repository import InMemoryVideoQueueRepository
from tests.conftest import signed_headers


class FakeImageService:
    async def detect_base64(self, image_base64: str, *, prompt: str | None = None) -> dict[str, object]:
        return {
            "top_category": "safe",
            "is_nsfw": False,
            "overall_severity": 0,
            "categories": {
                "safe": 0,
                "suggestive": 0,
                "nudity": 0,
                "porn": 0,
                "gore": 0,
                "violence": 0,
                "self_harm": 0,
                "hate_or_extremism": 0,
                "drugs": 0,
                "unknown": 0,
                "sexual_minor_content": 0,
            },
            "reason": f"fixture bytes {len(base64.b64decode(image_base64))} prompt {prompt or 'none'}",
        }

    async def detect_url(self, image_url: str, *, prompt: str | None = None) -> dict[str, object]:
        return {
            "top_category": "safe",
            "is_nsfw": False,
            "overall_severity": 0,
            "categories": {
                "safe": 0,
                "suggestive": 0,
                "nudity": 0,
                "porn": 0,
                "gore": 0,
                "violence": 0,
                "self_harm": 0,
                "hate_or_extremism": 0,
                "drugs": 0,
                "unknown": 0,
                "sexual_minor_content": 0,
            },
            "reason": f"fixture url {image_url} prompt {prompt or 'none'}",
        }


@pytest.mark.asyncio
async def test_image_base64_endpoint_uses_stateless_service(test_settings) -> None:  # type: ignore[no-untyped-def]
    app = create_app(
        settings=test_settings,
        queue_repository=InMemoryVideoQueueRepository(),
    )
    app.state.image_detection_service = FakeImageService()
    body = {"image_base64": base64.b64encode(b"image").decode("ascii"), "prompt": "make a dance video"}
    raw_body, headers = signed_headers(method="POST", path="/v1/images/detect-base64", body=body)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/images/detect-base64", content=raw_body, headers=headers)

    assert response.status_code == 200
    assert response.json() == {
        "top_category": "safe",
        "is_nsfw": False,
        "overall_severity": 0,
        "categories": {
            "safe": 0,
            "suggestive": 0,
            "nudity": 0,
            "porn": 0,
            "gore": 0,
            "violence": 0,
            "self_harm": 0,
            "hate_or_extremism": 0,
            "drugs": 0,
            "unknown": 0,
            "sexual_minor_content": 0,
        },
        "reason": "fixture bytes 5 prompt make a dance video",
    }
