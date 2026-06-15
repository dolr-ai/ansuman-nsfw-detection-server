from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from anyio import to_thread

from app.config.settings import Settings
from app.schemas.clickhouse import ExcludedVideoRow
from app.schemas.legacy import LegacyNsfwAggRow
from app.schemas.video import VideoBanRequest


class ExcludedVideosRepository(Protocol):
    def insert_rows(self, table_name: str, rows: list[ExcludedVideoRow]) -> None: ...


class LegacyNsfwAggRepository(Protocol):
    def insert_rows(self, table_name: str, rows: list[LegacyNsfwAggRow]) -> None: ...


@dataclass(frozen=True)
class ManualBanResult:
    video_id: str
    status: str
    excluded_videos_written: bool
    legacy_nsfw_agg_written: bool
    trace_id: str | None


class ManualBanService:
    def __init__(
        self,
        *,
        settings: Settings,
        excluded_videos_repository: ExcludedVideosRepository,
        legacy_repository: LegacyNsfwAggRepository,
    ) -> None:
        self._settings = settings
        self._excluded_videos_repository = excluded_videos_repository
        self._legacy_repository = legacy_repository

    async def ban_video(self, video_id: str, request: VideoBanRequest) -> ManualBanResult:
        now = datetime.now(UTC)
        excluded_row = ExcludedVideoRow(
            video_id=video_id,
            excluded_at=now,
            exclusion_reason="banned",
            updated_at_replacing=now,
        )
        legacy_row = LegacyNsfwAggRow(
            video_id=video_id,
            gcs_video_id=None,
            nsfw_ec="explicit",
            nsfw_gore="VERY_UNLIKELY",
            is_nsfw=True,
            probability=1.0,
        )

        # Manual bans are synchronous because off-chain shows success only after these facts are durable.
        # Write the recsys exclusion last so a partial failure does not publish exclusion before compatibility data.
        await to_thread.run_sync(
            self._legacy_repository.insert_rows,
            self._settings.clickhouse_nsfw_agg_table,
            [legacy_row],
        )
        await to_thread.run_sync(
            self._excluded_videos_repository.insert_rows,
            self._settings.clickhouse_excluded_videos_table,
            [excluded_row],
        )

        return ManualBanResult(
            video_id=video_id,
            status="banned",
            excluded_videos_written=True,
            legacy_nsfw_agg_written=True,
            trace_id=request.trace_id,
        )
