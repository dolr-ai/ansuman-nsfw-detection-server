import sqlalchemy as sa

from app.models.frame_result import FrameModerationResult
from app.repositories.postgres.base import PostgresRepository
from app.repositories.postgres.tables import nsfw_frame_results


class FrameResultRepository(PostgresRepository):
    async def insert_frame_results(
        self,
        *,
        job_id: str,
        video_id: str,
        prompt_version: str,
        model_provider: str,
        model_name: str,
        model_version: str | None,
        frames: list[FrameModerationResult],
    ) -> None:
        if not frames:
            return
        rows = [
            frame_result_to_row(
                job_id=job_id,
                video_id=video_id,
                prompt_version=prompt_version,
                model_provider=model_provider,
                model_name=model_name,
                model_version=model_version,
                frame=frame,
            )
            for frame in frames
        ]
        await self.execute(sa.insert(nsfw_frame_results).values(rows))


def frame_result_to_row(
    *,
    job_id: str,
    video_id: str,
    prompt_version: str,
    model_provider: str,
    model_name: str,
    model_version: str | None,
    frame: FrameModerationResult,
) -> dict[str, object]:
    categories = frame.categories
    return {
        "frame_id": f"{job_id}:{frame.frame_index}",
        "job_id": job_id,
        "video_id": video_id,
        "frame_index": frame.frame_index,
        "frame_timestamp_seconds": frame.frame_timestamp_seconds,
        "frame_hash": None,
        "prompt_version": prompt_version,
        "model_provider": model_provider,
        "model_name": model_name,
        "model_version": model_version,
        "top_category": frame.top_category,
        "is_nsfw": frame.is_nsfw,
        "overall_severity": frame.overall_severity,
        "safe_severity": categories["safe"],
        "suggestive_severity": categories["suggestive"],
        "nudity_severity": categories["nudity"],
        "porn_severity": categories["porn"],
        "gore_severity": categories["gore"],
        "violence_severity": categories["violence"],
        "self_harm_severity": categories["self_harm"],
        "hate_or_extremism_severity": categories["hate_or_extremism"],
        "drugs_severity": categories["drugs"],
        "unknown_severity": categories["unknown"],
        "sexual_minor_content_severity": categories["sexual_minor_content"],
        "reason": frame.reason,
        "raw_response": frame.raw_response,
    }
