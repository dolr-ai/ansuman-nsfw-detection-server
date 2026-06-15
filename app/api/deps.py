from typing import Annotated

from fastapi import Header, Request

from app.config.settings import Settings
from app.errors.base import AppError
from app.errors.codes import SERVICE_UNAVAILABLE
from app.schemas.auth import SignedRequestContext
from app.services.auth_service import AuthService
from app.services.image_detection_service import ImageDetectionService
from app.services.manual_ban_service import ManualBanService
from app.services.queue_service import QueueService
from app.services.readiness_service import ReadinessService
from app.services.text_detection_service import TextDetectionService
from app.services.video_status_service import VideoStatusService


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


def get_video_status_service(request: Request) -> VideoStatusService:
    return request.app.state.video_status_service


def get_manual_ban_service(request: Request) -> ManualBanService:
    service = getattr(request.app.state, "manual_ban_service", None)
    if service is None:
        raise AppError(
            SERVICE_UNAVAILABLE,
            "manual ban service is not configured",
            status_code=503,
        )
    return service


async def require_signed_request(
    request: Request,
    x_internal_timestamp: Annotated[
        str,
        Header(
            alias="X-Internal-Timestamp",
            description=(
                "Unix epoch seconds. The HMAC message is `<timestamp>\\n<METHOD>\\n<path>\\n<SHA256(raw_body)>`."
            ),
        ),
    ],
    x_internal_signature: Annotated[
        str,
        Header(
            alias="X-Internal-Signature",
            description="Hex HMAC-SHA256 signature using the internal shared secret.",
        ),
    ],
) -> SignedRequestContext:
    _ = (x_internal_timestamp, x_internal_signature)
    auth_service: AuthService = request.app.state.auth_service
    return await auth_service.authenticate(
        method=request.method,
        path=request.url.path,
        headers=request.headers,
        raw_body=await request.body(),
    )
