from app.clients.storj_interface import StorjInterfaceClient
from app.models.video_result import VideoModerationResult
from app.schemas.storage_action import StorjMoveResponse


class StorageMoveService:
    def __init__(self, storj_client: StorjInterfaceClient) -> None:
        self._storj_client = storj_client

    async def move_if_required(
        self,
        *,
        result: VideoModerationResult,
        publisher_user_id: str,
    ) -> StorjMoveResponse | None:
        if not result.move_required:
            return None
        return await self._storj_client.move_to_nsfw(
            publisher_user_id=publisher_user_id,
            video_id=result.video_id,
        )

