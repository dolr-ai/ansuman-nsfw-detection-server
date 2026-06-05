import httpx

from app.config.settings import Settings
from app.errors.base import AppError
from app.schemas.storage_action import StorjMoveResponse


class StorjInterfaceClient:
    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http_client = http_client

    async def move_to_nsfw(self, publisher_user_id: str, video_id: str) -> StorjMoveResponse:
        if not self._settings.storj_interface_url or not self._settings.storj_interface_token:
            raise AppError("storj_not_configured", "Storj interface is not configured", status_code=503)

        url = f"{self._settings.storj_interface_url.rstrip('/')}/move-to-nsfw"
        response = await self._http_client.post(
            url,
            json={"publisher_user_id": publisher_user_id, "video_id": video_id},
            headers={"Authorization": f"Bearer {self._settings.storj_interface_token.get_secret_value()}"},
            timeout=self._settings.storj_interface_timeout_seconds,
        )
        response.raise_for_status()
        return StorjMoveResponse(status_code=response.status_code, body=response.text)

