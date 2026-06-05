from app.config.settings import Settings
from app.repositories.kvrocks.clickhouse_buffer_repository import ClickHouseBufferRepository
from app.schemas.clickhouse import VideoNsfwDetectionRow
from app.schemas.legacy import LegacyNsfwAggRow
from app.schemas.storage_action import StorageActionRow


class ClickHouseFlushService:
    def __init__(
        self,
        *,
        settings: Settings,
        buffer_repository: ClickHouseBufferRepository,
        video_result_repository,
        legacy_repository,
        storage_action_repository,
        batch_size: int = 50,
    ) -> None:  # type: ignore[no-untyped-def]
        self._settings = settings
        self._buffer_repository = buffer_repository
        self._video_result_repository = video_result_repository
        self._legacy_repository = legacy_repository
        self._storage_action_repository = storage_action_repository
        self._batch_size = batch_size

    async def flush_once(self) -> None:
        await self._flush_video_results()
        await self._flush_legacy_rows()
        await self._flush_storage_actions()

    async def _flush_video_results(self) -> None:
        rows = await self._buffer_repository.read_batch(
            self._settings.clickhouse_buffer_video_results_key,
            self._batch_size,
        )
        if not rows:
            return
        parsed = [VideoNsfwDetectionRow.model_validate(row) for row in rows]
        self._video_result_repository.insert_rows(self._settings.clickhouse_nsfw_table, parsed)
        await self._buffer_repository.trim_batch(self._settings.clickhouse_buffer_video_results_key, len(rows))

    async def _flush_legacy_rows(self) -> None:
        rows = await self._buffer_repository.read_batch(self._settings.clickhouse_buffer_legacy_key, self._batch_size)
        if not rows:
            return
        parsed = [LegacyNsfwAggRow.model_validate(row) for row in rows]
        self._legacy_repository.insert_rows(self._settings.clickhouse_nsfw_agg_table, parsed)
        await self._buffer_repository.trim_batch(self._settings.clickhouse_buffer_legacy_key, len(rows))

    async def _flush_storage_actions(self) -> None:
        rows = await self._buffer_repository.read_batch(
            self._settings.clickhouse_buffer_storage_actions_key,
            self._batch_size,
        )
        if not rows:
            return
        parsed = [StorageActionRow.model_validate(row) for row in rows]
        self._storage_action_repository.insert_rows(self._settings.clickhouse_storage_actions_table, parsed)
        await self._buffer_repository.trim_batch(self._settings.clickhouse_buffer_storage_actions_key, len(rows))
