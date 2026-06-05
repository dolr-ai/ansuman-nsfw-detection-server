import asyncio
import logging

from app.clients.clickhouse import create_clickhouse_client
from app.clients.kvrocks import create_kvrocks_client
from app.config.settings import Settings
from app.repositories.clickhouse.legacy_nsfw_agg_repository import ClickHouseLegacyNsfwAggRepository
from app.repositories.clickhouse.storage_action_repository import ClickHouseStorageActionRepository
from app.repositories.clickhouse.video_result_repository import ClickHouseVideoResultRepository
from app.repositories.kvrocks.clickhouse_buffer_repository import RedisClickHouseBufferRepository
from app.services.clickhouse_flush_service import ClickHouseFlushService


async def run() -> None:
    logging.getLogger(__name__).info("clickhouse flush worker skeleton started")
    settings = Settings()
    redis_client = create_kvrocks_client(settings)
    clickhouse_client = create_clickhouse_client(settings)
    flush_service = ClickHouseFlushService(
        settings=settings,
        buffer_repository=RedisClickHouseBufferRepository(redis_client),
        video_result_repository=ClickHouseVideoResultRepository(clickhouse_client, settings.clickhouse_database),
        legacy_repository=ClickHouseLegacyNsfwAggRepository(clickhouse_client, settings.clickhouse_database),
        storage_action_repository=ClickHouseStorageActionRepository(clickhouse_client, settings.clickhouse_database),
    )
    await flush_service.flush_once()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
