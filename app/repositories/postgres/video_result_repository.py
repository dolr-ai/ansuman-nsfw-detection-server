import sqlalchemy as sa

from app.models.video_result import VideoModerationResult
from app.repositories.postgres.base import PostgresRepository
from app.repositories.postgres.tables import nsfw_video_results


class VideoResultRepository(PostgresRepository):
    async def insert_final_result(self, result: VideoModerationResult) -> None:
        await self.execute(sa.insert(nsfw_video_results).values(**video_result_to_row(result)))


def video_result_to_row(result: VideoModerationResult) -> dict[str, object]:
    return {
        "job_id": result.job_id,
        "video_id": result.video_id,
        "policy_version": result.policy_version,
        "prompt_version": result.prompt_version,
        "aggregation_version": result.aggregation_version,
        "final_is_nsfw": result.final_is_nsfw,
        "final_score": result.final_score,
        "final_top_category": result.final_top_category,
        "max_overall_severity": result.max_overall_severity,
        "nsfw_frame_count": result.nsfw_frame_count,
        "total_frame_count": result.total_frame_count,
        "move_required": result.move_required,
        "move_threshold": result.move_threshold,
        "legacy_nsfw_ec": result.legacy_nsfw_ec,
        "legacy_nsfw_gore": result.legacy_nsfw_gore,
        "final_response": result.final_response,
        "created_at": result.created_at,
        "updated_at": result.updated_at,
    }
