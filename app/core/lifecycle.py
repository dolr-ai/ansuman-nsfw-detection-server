from collections.abc import Callable
from pathlib import Path

from app.clients.gpu_openai import GpuOpenAIClient
from app.clients.kvrocks import create_kvrocks_client
from app.config.settings import Settings
from app.repositories.kvrocks.auth_nonce_repository import InMemoryAuthNonceRepository, RedisAuthNonceRepository
from app.repositories.kvrocks.queue_repository import InMemoryVideoQueueRepository, RedisVideoQueueRepository
from app.services.auth_service import AuthService
from app.services.gpu_moderation_service import GpuModerationService
from app.services.queue_service import QueueService


def build_auth_service(settings: Settings) -> AuthService:
    if settings.is_kvrocks_configured():
        redis_client = create_kvrocks_client(settings)
        nonce_repository = RedisAuthNonceRepository(redis_client)
    else:
        nonce_repository = InMemoryAuthNonceRepository()
    return AuthService(settings=settings, nonce_repository=nonce_repository)


def build_queue_service(settings: Settings) -> QueueService:
    if settings.is_kvrocks_configured():
        redis_client = create_kvrocks_client(settings)
        queue_repository = RedisVideoQueueRepository(redis_client, settings=settings)
    else:
        queue_repository = InMemoryVideoQueueRepository()
    return QueueService(queue_repository=queue_repository)


def build_gpu_moderation_service(settings: Settings) -> GpuModerationService | None:
    if not settings.is_gpu_configured():
        return None
    prompt_path = Path(__file__).resolve().parents[1] / "prompts" / f"{settings.visual_prompt_version}.txt"
    text_prompt_path = Path(__file__).resolve().parents[1] / "prompts" / f"{settings.text_prompt_version}.txt"
    client = GpuOpenAIClient(settings)
    return GpuModerationService(
        settings=settings,
        visual_client=client,
        visual_prompt=prompt_path.read_text(encoding="utf-8"),
        text_client=client,
        text_prompt=text_prompt_path.read_text(encoding="utf-8"),
    )


ReadinessCheck = Callable[[], dict[str, object]]
