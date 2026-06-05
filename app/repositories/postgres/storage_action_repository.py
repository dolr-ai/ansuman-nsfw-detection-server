import sqlalchemy as sa

from app.models.storage_action import StorageAction
from app.repositories.postgres.base import PostgresRepository
from app.repositories.postgres.tables import nsfw_storage_actions


class StorageActionRepository(PostgresRepository):
    async def insert_storage_action(self, action: StorageAction) -> None:
        await self.execute(sa.insert(nsfw_storage_actions).values(**storage_action_to_row(action)))


def storage_action_to_row(action: StorageAction) -> dict[str, object]:
    return {
        "action_id": action.action_id,
        "job_id": action.job_id,
        "video_id": action.video_id,
        "publisher_user_id": action.publisher_user_id,
        "action_type": action.action_type,
        "threshold": action.threshold,
        "final_score": action.final_score,
        "request_url": action.request_url,
        "request_body": action.request_body,
        "response_status": action.response_status,
        "response_body": action.response_body,
        "status": action.status,
        "created_at": action.created_at,
        "completed_at": action.completed_at,
    }
