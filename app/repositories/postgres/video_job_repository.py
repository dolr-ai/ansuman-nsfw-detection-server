from dataclasses import asdict

import sqlalchemy as sa

from app.core.constants import VideoJobStatus
from app.models.video_job import VideoJob
from app.repositories.postgres.base import PostgresRepository
from app.repositories.postgres.tables import nsfw_video_jobs


class VideoJobRepository(PostgresRepository):
    async def insert_video_job(self, job: VideoJob) -> None:
        await self.execute(sa.insert(nsfw_video_jobs).values(**video_job_to_row(job)))

    async def get_by_job_id(self, job_id: str) -> VideoJob | None:
        result = await self.execute(sa.select(nsfw_video_jobs).where(nsfw_video_jobs.c.job_id == job_id))
        row = result.mappings().first()
        return row_to_video_job(row) if row is not None else None

    async def get_latest_by_video_id(self, video_id: str) -> VideoJob | None:
        result = await self.execute(
            sa.select(nsfw_video_jobs)
            .where(nsfw_video_jobs.c.video_id == video_id)
            .order_by(nsfw_video_jobs.c.updated_at.desc())
            .limit(1)
        )
        row = result.mappings().first()
        return row_to_video_job(row) if row is not None else None

    async def mark_processing(self, job_id: str) -> None:
        await self.execute(
            sa.update(nsfw_video_jobs)
            .where(nsfw_video_jobs.c.job_id == job_id)
            .values(
                status=VideoJobStatus.PROCESSING.value,
                attempts=nsfw_video_jobs.c.attempts + 1,
                started_at=sa.func.now(),
                updated_at=sa.func.now(),
            )
        )

    async def mark_classified(self, job_id: str) -> None:
        await self.execute(
            sa.update(nsfw_video_jobs)
            .where(nsfw_video_jobs.c.job_id == job_id)
            .values(
                status=VideoJobStatus.CLASSIFIED.value,
                finished_at=sa.func.now(),
                updated_at=sa.func.now(),
            )
        )

    async def mark_failed(
        self,
        job_id: str,
        *,
        status: VideoJobStatus,
        error_code: str,
        error_message: str,
    ) -> None:
        if status not in {VideoJobStatus.FAILED_RETRYABLE, VideoJobStatus.FAILED_TERMINAL}:
            raise ValueError("failed status must be retryable or terminal")
        await self.execute(
            sa.update(nsfw_video_jobs)
            .where(nsfw_video_jobs.c.job_id == job_id)
            .values(
                status=status.value,
                last_error_code=error_code,
                last_error_message=error_message,
                finished_at=sa.func.now() if status == VideoJobStatus.FAILED_TERMINAL else None,
                updated_at=sa.func.now(),
            )
        )


def video_job_to_row(job: VideoJob) -> dict[str, object]:
    row = asdict(job)
    row["status"] = job.status.value
    return row


def row_to_video_job(row) -> VideoJob:  # type: ignore[no-untyped-def]
    data = dict(row)
    data["status"] = VideoJobStatus(data["status"])
    return VideoJob(**data)
