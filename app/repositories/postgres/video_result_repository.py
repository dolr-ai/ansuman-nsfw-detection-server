import sqlalchemy as sa

from app.models.video_result import VideoModerationResult
from app.repositories.postgres.base import PostgresRepository
from app.repositories.postgres.tables import nsfw_video_results


class VideoResultRepository(PostgresRepository):
    async def insert_final_result(self, result: VideoModerationResult) -> None:
        await self.execute(sa.insert(nsfw_video_results).values(**video_result_to_row(result)))

    async def get_by_job_id(self, job_id: str) -> VideoModerationResult | None:
        result = await self.execute(sa.select(nsfw_video_results).where(nsfw_video_results.c.job_id == job_id))
        row = result.mappings().first()
        return row_to_video_result(row) if row is not None else None

    async def get_latest_by_video_id(self, video_id: str) -> VideoModerationResult | None:
        result = await self.execute(
            sa.select(nsfw_video_results)
            .where(nsfw_video_results.c.video_id == video_id)
            .order_by(nsfw_video_results.c.updated_at.desc())
            .limit(1)
        )
        row = result.mappings().first()
        return row_to_video_result(row) if row is not None else None


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


def row_to_video_result(row) -> VideoModerationResult:  # type: ignore[no-untyped-def]
    data = dict(row)
    final_response = data.get("final_response") or {}
    raw_max_category_severities = {}
    if isinstance(final_response, dict):
        raw_max_category_severities = final_response.get("max_category_severities") or {}

    max_category_severities = {
        str(category): int(severity)
        for category, severity in raw_max_category_severities.items()
    }

    return VideoModerationResult(
        job_id=data["job_id"],
        video_id=data["video_id"],
        policy_version=data["policy_version"],
        prompt_version=data["prompt_version"],
        aggregation_version=data["aggregation_version"],
        final_is_nsfw=data["final_is_nsfw"],
        final_score=data["final_score"],
        final_top_category=data["final_top_category"],
        max_overall_severity=data["max_overall_severity"],
        nsfw_frame_count=data["nsfw_frame_count"],
        total_frame_count=data["total_frame_count"],
        move_required=data["move_required"],
        move_threshold=data["move_threshold"],
        max_category_severities=max_category_severities,
        legacy_nsfw_ec=data["legacy_nsfw_ec"],
        legacy_nsfw_gore=data["legacy_nsfw_gore"],
        final_response=final_response,
        created_at=data["created_at"],
        updated_at=data["updated_at"],
    )
