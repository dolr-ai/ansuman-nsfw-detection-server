import httpx
import pytest
from pydantic import SecretStr

from app.clients.storj_interface import StorjInterfaceClient


@pytest.mark.asyncio
async def test_storj_client_sends_bearer_auth_and_move_body(test_settings) -> None:  # type: ignore[no-untyped-def]
    seen: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers["authorization"]
        seen["body"] = request.read().decode("utf-8")
        return httpx.Response(200, text="ok")

    settings = test_settings.model_copy(
        update={
            "storj_interface_url": "https://storj.local",
            "storj_interface_token": SecretStr("token"),
        }
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        response = await StorjInterfaceClient(settings, http_client).move_to_nsfw(
            publisher_user_id="user",
            video_id="video",
        )

    assert response.status_code == 200
    assert seen["url"] == "https://storj.local/move-to-nsfw"
    assert seen["authorization"] == "Bearer token"
    assert seen["body"] == '{"publisher_user_id":"user","video_id":"video"}'

