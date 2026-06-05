from fastapi import Request

from app.config.settings import Settings
from app.schemas.auth import SignedRequestContext
from app.services.auth_service import AuthService
from app.services.image_detection_service import ImageDetectionService
from app.services.queue_service import QueueService
from app.services.readiness_service import ReadinessService
from app.services.text_detection_service import TextDetectionService


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_queue_service(request: Request) -> QueueService:
    return request.app.state.queue_service


def get_readiness_service(request: Request) -> ReadinessService:
    return request.app.state.readiness_service


def get_image_detection_service(request: Request) -> ImageDetectionService:
    return request.app.state.image_detection_service


def get_text_detection_service(request: Request) -> TextDetectionService:
    return request.app.state.text_detection_service


async def require_signed_request(request: Request) -> SignedRequestContext:
    auth_service: AuthService = request.app.state.auth_service
    return await auth_service.authenticate(
        method=request.method,
        path=request.url.path,
        headers=request.headers,
        raw_body=await request.body(),
    )

