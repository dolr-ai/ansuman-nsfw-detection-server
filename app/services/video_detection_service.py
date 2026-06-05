import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from app.config.settings import Settings
from app.core.constants import VideoJobStatus
from app.models.frame_result import FrameModerationResult
from app.models.storage_action import StorageAction
from app.models.video_job import VideoJob
from app.models.video_metadata import VideoMetadata
from app.models.video_result import VideoModerationResult
from app.repositories.kvrocks.clickhouse_buffer_repository import ClickHouseBufferRepository
from app.repositories.kvrocks.runtime_nsfw_repository import RuntimeNsfwRepository
from app.schemas.clickhouse import VideoNsfwDetectionRow
from app.schemas.storage_action import StorageActionRow, StorjMoveResponse
from app.services.legacy_mapping_service import to_legacy_nsfw_agg
from app.services.storage_move_service import StorageMoveService


class FinalResultUnitOfWork(Protocol):
    async def __aenter__(self) -> "FinalResultUnitOfWork":
        ...

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        ...

    async def insert_frame_results(
        self,
        *,
        job: VideoJob,
        result: VideoModerationResult,
        frames: list[FrameModerationResult],
        settings: Settings,
    ) -> None:
        ...

    async def insert_final_result(self, result: VideoModerationResult) -> None:
        ...

    async def insert_storage_action(self, action: StorageAction) -> None:
        ...

    async def mark_job_classified(self, job_id: str) -> None:
        ...


@dataclass(frozen=True)
class FinalizationResult:
    storage_action: StorageAction | None


class VideoDetectionService:
    def __init__(
        self,
        *,
        settings: Settings,
        storage_move_service: StorageMoveService,
        unit_of_work_factory: Callable[[], FinalResultUnitOfWork],
        clickhouse_buffer_repository: ClickHouseBufferRepository,
        runtime_repository: RuntimeNsfwRepository,
    ) -> None:
        self._settings = settings
        self._storage_move_service = storage_move_service
        self._unit_of_work_factory = unit_of_work_factory
        self._clickhouse_buffer_repository = clickhouse_buffer_repository
        self._runtime_repository = runtime_repository

    async def finalize_classification(
        self,
        *,
        job: VideoJob,
        metadata: VideoMetadata,
        frames: list[FrameModerationResult],
        result: VideoModerationResult,
    ) -> FinalizationResult:
        move_response = await self._move_before_final_commit(job=job, result=result)
        storage_action = self._storage_action(job=job, result=result, move_response=move_response)

        async with self._unit_of_work_factory() as unit_of_work:
            await unit_of_work.insert_frame_results(job=job, result=result, frames=frames, settings=self._settings)
            await unit_of_work.insert_final_result(result)
            if storage_action is not None:
                await unit_of_work.insert_storage_action(storage_action)
            await unit_of_work.mark_job_classified(job.job_id)

        await self._publish_after_commit(
            job=job,
            metadata=metadata,
            frames=frames,
            result=result,
            storage_action=storage_action,
        )
        return FinalizationResult(storage_action=storage_action)

    async def _move_before_final_commit(
        self,
        *,
        job: VideoJob,
        result: VideoModerationResult,
    ) -> StorjMoveResponse | None:
        return await self._storage_move_service.move_if_required(
            result=result,
            publisher_user_id=job.publisher_user_id,
        )

    def _storage_action(
        self,
        *,
        job: VideoJob,
        result: VideoModerationResult,
        move_response: StorjMoveResponse | None,
    ) -> StorageAction | None:
        if move_response is None:
            return None
        now = datetime.now(UTC)
        request_url = ""
        if self._settings.storj_interface_url:
            request_url = f"{self._settings.storj_interface_url.rstrip('/')}/move-to-nsfw"
        return StorageAction(
            action_id=f"storage-action:{job.job_id}:{uuid4()}",
            job_id=job.job_id,
            video_id=job.video_id,
            publisher_user_id=job.publisher_user_id,
            action_type="move_to_nsfw",
            threshold=result.move_threshold,
            final_score=result.final_score,
            request_url=request_url,
            request_body={"publisher_user_id": job.publisher_user_id, "video_id": job.video_id},
            response_status=move_response.status_code,
            response_body=move_response.body,
            status="succeeded",
            created_at=now,
            completed_at=now,
        )

    async def _publish_after_commit(
        self,
        *,
        job: VideoJob,
        metadata: VideoMetadata,
        frames: list[FrameModerationResult],
        result: VideoModerationResult,
        storage_action: StorageAction | None,
    ) -> None:
        canonical_row = to_clickhouse_video_row(
            job=job,
            metadata=metadata,
            frames=frames,
            result=result,
            settings=self._settings,
            storage_action=storage_action,
        )
        await self._clickhouse_buffer_repository.push_json(
            self._settings.clickhouse_buffer_video_results_key,
            canonical_row.model_dump(mode="json"),
        )
        legacy_row = to_legacy_nsfw_agg(result)
        await self._clickhouse_buffer_repository.push_json(
            self._settings.clickhouse_buffer_legacy_key,
            legacy_row.model_dump(mode="json"),
        )
        if storage_action is not None:
            storage_row = to_clickhouse_storage_action_row(storage_action)
            await self._clickhouse_buffer_repository.push_json(
                self._settings.clickhouse_buffer_storage_actions_key,
                storage_row.model_dump(mode="json"),
            )
        await self._runtime_repository.write_result(job.video_id, runtime_nsfw_payload(result))


def runtime_nsfw_payload(result: VideoModerationResult) -> dict[str, object]:
    return {
        "video_id": result.video_id,
        "is_nsfw": result.final_is_nsfw,
        "probability": result.final_score,
        "nsfw_ec": result.legacy_nsfw_ec,
        "nsfw_gore": result.legacy_nsfw_gore,
        "policy_version": result.policy_version,
        "status": VideoJobStatus.CLASSIFIED.value,
    }


def to_clickhouse_video_row(
    *,
    job: VideoJob,
    metadata: VideoMetadata,
    frames: list[FrameModerationResult],
    result: VideoModerationResult,
    settings: Settings,
    storage_action: StorageAction | None,
) -> VideoNsfwDetectionRow:
    now = datetime.now(UTC)
    max_categories = result.max_category_severities
    return VideoNsfwDetectionRow(
        video_id=job.video_id,
        job_id=job.job_id,
        publisher_user_id=job.publisher_user_id,
        post_id=job.post_id,
        canister_id=job.canister_id,
        source_video_uri=job.source_video_uri,
        source_object_version=job.source_object_version,
        upload_event_id=job.upload_event_id,
        status=VideoJobStatus.CLASSIFIED.value,
        policy_version=result.policy_version,
        prompt_version=result.prompt_version,
        aggregation_version=result.aggregation_version,
        model_provider=settings.model_provider,
        model_name=settings.model_name or "",
        model_version=settings.model_version,
        duration_seconds=metadata.duration_seconds,
        frames_extracted=metadata.frames_extracted or len(frames),
        frames_processed=len(frames),
        frame_batch_size=settings.frame_batch_size,
        final_is_nsfw=result.final_is_nsfw,
        final_score=result.final_score,
        final_top_category=result.final_top_category,
        max_overall_severity=result.max_overall_severity,
        nsfw_frame_count=result.nsfw_frame_count,
        total_frame_count=result.total_frame_count,
        max_suggestive_severity=max_categories.get("suggestive", 0),
        max_nudity_severity=max_categories.get("nudity", 0),
        max_porn_severity=max_categories.get("porn", 0),
        max_gore_severity=max_categories.get("gore", 0),
        max_violence_severity=max_categories.get("violence", 0),
        max_self_harm_severity=max_categories.get("self_harm", 0),
        max_hate_or_extremism_severity=max_categories.get("hate_or_extremism", 0),
        max_drugs_severity=max_categories.get("drugs", 0),
        max_unknown_severity=max_categories.get("unknown", 0),
        max_sexual_minor_content_severity=max_categories.get("sexual_minor_content", 0),
        move_required=result.move_required,
        move_threshold=result.move_threshold,
        storj_move_status=storage_action.status if storage_action is not None else "not_required",
        legacy_nsfw_ec=result.legacy_nsfw_ec,
        legacy_nsfw_gore=result.legacy_nsfw_gore,
        frame_results_json=json.dumps([frame.raw_response for frame in frames], separators=(",", ":")),
        final_response_json=json.dumps(result.final_response, separators=(",", ":")),
        created_at=result.created_at,
        updated_at=result.updated_at,
        updated_at_replacing=now,
    )


def to_clickhouse_storage_action_row(action: StorageAction) -> StorageActionRow:
    return StorageActionRow(
        action_id=action.action_id,
        video_id=action.video_id,
        job_id=action.job_id,
        publisher_user_id=action.publisher_user_id,
        action_type=action.action_type,
        threshold=action.threshold,
        final_score=action.final_score,
        status=action.status,
        request_url=action.request_url,
        request_body_json=json.dumps(action.request_body, separators=(",", ":")),
        response_status=action.response_status,
        response_body=action.response_body or "",
        created_at=action.created_at,
        completed_at=action.completed_at,
        updated_at_replacing=datetime.now(UTC),
    )
