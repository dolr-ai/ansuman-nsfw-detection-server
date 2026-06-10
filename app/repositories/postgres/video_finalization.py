from typing import Protocol

from sqlalchemy.dialects.postgresql import insert as postgres_insert

from app.config.settings import Settings
from app.core.constants import VideoJobStatus
from app.models.frame_result import FrameModerationResult
from app.models.storage_action import StorageAction
from app.models.video_job import VideoJob
from app.models.video_result import VideoModerationResult
from app.repositories.postgres.frame_result_repository import FrameResultRepository
from app.repositories.postgres.storage_action_repository import StorageActionRepository
from app.repositories.postgres.tables import nsfw_video_jobs
from app.repositories.postgres.video_job_repository import VideoJobRepository, video_job_to_row
from app.repositories.postgres.video_result_repository import VideoResultRepository


class VideoJobStateRepository(Protocol):
    async def get_by_job_id(self, job_id: str) -> VideoJob | None:
        ...

    async def mark_processing(self, job: VideoJob) -> None:
        ...

    async def mark_failed(
        self,
        job_id: str,
        *,
        status: VideoJobStatus,
        error_code: str,
        error_message: str,
    ) -> None:
        ...


class PostgresVideoJobStateRepository:
    def __init__(self, session_factory) -> None:  # type: ignore[no-untyped-def]
        self._session_factory = session_factory

    async def get_by_job_id(self, job_id: str) -> VideoJob | None:
        async with self._session_factory() as session:
            return await VideoJobRepository(session).get_by_job_id(job_id)

    async def mark_processing(self, job: VideoJob) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    postgres_insert(nsfw_video_jobs)
                    .values(**video_job_to_row(job))
                    .on_conflict_do_nothing()
                )
                await VideoJobRepository(session).mark_processing(job.job_id)

    async def mark_failed(
        self,
        job_id: str,
        *,
        status: VideoJobStatus,
        error_code: str,
        error_message: str,
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await VideoJobRepository(session).mark_failed(
                    job_id,
                    status=status,
                    error_code=error_code,
                    error_message=error_message,
                )


class PostgresFinalResultUnitOfWork:
    def __init__(self, session_factory) -> None:  # type: ignore[no-untyped-def]
        self._session_factory = session_factory
        self._session_context = None
        self._transaction_context = None
        self._session = None

    async def __aenter__(self) -> "PostgresFinalResultUnitOfWork":
        self._session_context = self._session_factory()
        self._session = await self._session_context.__aenter__()
        self._transaction_context = self._session.begin()
        await self._transaction_context.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        try:
            if self._transaction_context is not None:
                await self._transaction_context.__aexit__(exc_type, exc, tb)
        finally:
            if self._session_context is not None:
                await self._session_context.__aexit__(exc_type, exc, tb)

    async def insert_frame_results(
        self,
        *,
        job: VideoJob,
        result: VideoModerationResult,
        frames: list[FrameModerationResult],
        settings: Settings,
    ) -> None:
        await FrameResultRepository(self._required_session()).insert_frame_results(
            job_id=job.job_id,
            video_id=job.video_id,
            prompt_version=result.prompt_version,
            model_provider=settings.model_provider,
            model_name=settings.model_name or "",
            model_version=settings.model_version,
            frames=frames,
        )

    async def insert_final_result(self, result: VideoModerationResult) -> None:
        await VideoResultRepository(self._required_session()).insert_final_result(result)

    async def insert_storage_action(self, action: StorageAction) -> None:
        await StorageActionRepository(self._required_session()).insert_storage_action(action)

    async def mark_job_classified(self, job_id: str) -> None:
        await VideoJobRepository(self._required_session()).mark_classified(job_id)

    def _required_session(self):  # type: ignore[no-untyped-def]
        if self._session is None:
            raise RuntimeError("unit of work has not been entered")
        return self._session
