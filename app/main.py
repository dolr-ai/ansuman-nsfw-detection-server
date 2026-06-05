from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.config.logging import configure_logging
from app.config.settings import Settings
from app.core.lifecycle import build_auth_service, build_gpu_moderation_service, build_queue_service
from app.core.sentry import init_sentry
from app.errors.base import AppError
from app.errors.http import (
    app_error_handler,
    http_error_handler,
    request_validation_error_handler,
    validation_error_handler,
)
from app.middleware.request_id import RequestIdMiddleware
from app.repositories.kvrocks.queue_repository import VideoQueueRepository
from app.services.image_detection_service import ImageDetectionService
from app.services.queue_service import QueueService
from app.services.readiness_service import ReadinessService
from app.services.text_detection_service import TextDetectionService


def create_app(
    *,
    settings: Settings | None = None,
    queue_repository: VideoQueueRepository | None = None,
) -> FastAPI:
    configure_logging()
    resolved_settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        init_sentry(resolved_settings)
        yield

    app = FastAPI(title=resolved_settings.app_name, lifespan=lifespan)

    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(ValidationError, validation_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)

    app.state.settings = resolved_settings
    app.state.auth_service = build_auth_service(resolved_settings)
    if queue_repository is not None:
        app.state.queue_service = QueueService(queue_repository)
    else:
        app.state.queue_service = build_queue_service(resolved_settings)

    app.state.readiness_service = ReadinessService(resolved_settings)
    gpu_service = build_gpu_moderation_service(resolved_settings)
    app.state.image_detection_service = ImageDetectionService(
        settings=resolved_settings,
        gpu_service=gpu_service,
    )
    app.state.text_detection_service = TextDetectionService(gpu_service=gpu_service)

    app.include_router(api_router)
    return app


app = create_app()
