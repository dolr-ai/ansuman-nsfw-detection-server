import logging
from collections.abc import Callable
from pathlib import Path

from clickhouse_connect.driver.exceptions import ClickHouseError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.clients.clickhouse import create_clickhouse_client
from app.clients.gpu_openai import GpuOpenAIClient
from app.clients.kvrocks import create_kvrocks_client
from app.clients.postgres import create_postgres_engine
from app.config.settings import Settings
from app.repositories.clickhouse.excluded_videos_repository import ClickHouseExcludedVideosRepository
from app.repositories.clickhouse.legacy_nsfw_agg_repository import ClickHouseLegacyNsfwAggRepository
from app.repositories.kvrocks.queue_repository import InMemoryVideoQueueRepository, RedisVideoQueueRepository
from app.services.auth_service import AuthService
from app.services.gpu_moderation_service import GpuModerationService
from app.services.manual_ban_service import ManualBanService
from app.services.queue_service import QueueService
from app.services.video_status_service import PostgresVideoResultReader, VideoResultReader, VideoStatusService

logger = logging.getLogger(__name__)


def build_auth_service(settings: Settings) -> AuthService:
    return AuthService(settings=settings)


def build_queue_service(settings: Settings) -> QueueService:
    if settings.is_kvrocks_configured():
        redis_client = create_kvrocks_client(settings)
        queue_repository = RedisVideoQueueRepository(redis_client, settings=settings)
    else:
        queue_repository = InMemoryVideoQueueRepository()
    return QueueService(queue_repository=queue_repository, settings=settings)


def build_video_status_service(
    settings: Settings,
    *,
    queue_service: QueueService,
    result_reader: VideoResultReader | None = None,
    use_postgres_reader: bool = True,
) -> VideoStatusService:
    resolved_result_reader = result_reader
    if resolved_result_reader is None and use_postgres_reader and settings.is_postgres_configured():
        engine = create_postgres_engine(settings)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        resolved_result_reader = PostgresVideoResultReader(session_factory)
    return VideoStatusService(queue_service=queue_service, result_reader=resolved_result_reader)


def build_manual_ban_service(settings: Settings) -> ManualBanService | None:
    if not settings.is_clickhouse_configured():
        return None
    try:
        clickhouse_client = create_clickhouse_client(settings)
    except ClickHouseError:
        logger.exception("manual ban service disabled because ClickHouse client initialization failed")
        return None
    return ManualBanService(
        settings=settings,
        excluded_videos_repository=ClickHouseExcludedVideosRepository(clickhouse_client, settings.clickhouse_database),
        legacy_repository=ClickHouseLegacyNsfwAggRepository(clickhouse_client, settings.clickhouse_database),
    )


def build_gpu_moderation_service(settings: Settings) -> GpuModerationService | None:
    if not settings.is_gpu_configured():
        return None
    prompts_dir = Path(__file__).resolve().parents[1] / "prompts"
    prompt_path = prompts_dir / f"{settings.visual_prompt_version}.txt"
    image_prompt_path = prompts_dir / f"{settings.image_prompt_version}.txt"
    image_text_prompt_path = prompts_dir / f"{settings.image_text_prompt_version}.txt"
    text_prompt_path = prompts_dir / f"{settings.text_prompt_version}.txt"
    client = GpuOpenAIClient(settings)
    return GpuModerationService(
        settings=settings,
        visual_client=client,
        visual_prompt=prompt_path.read_text(encoding="utf-8"),
        image_prompt=image_prompt_path.read_text(encoding="utf-8"),
        image_text_prompt=image_text_prompt_path.read_text(encoding="utf-8"),
        text_client=client,
        text_prompt=text_prompt_path.read_text(encoding="utf-8"),
    )


ReadinessCheck = Callable[[], dict[str, object]]
