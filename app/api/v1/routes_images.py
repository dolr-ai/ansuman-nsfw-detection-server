from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_image_detection_service
from app.schemas.image import ImageBase64DetectRequest, ImageUrlDetectRequest
from app.schemas.moderation import ModerationDetectResponse
from app.services.image_detection_service import ImageDetectionService

router = APIRouter(prefix="/images", tags=["images"])
ImageServiceDep = Annotated[ImageDetectionService, Depends(get_image_detection_service)]


@router.post(
    "/detect-url",
    response_model=ModerationDetectResponse,
    summary="Classify an image URL",
    description=(
        "Protected stateless endpoint. Validates the two internal HMAC headers, downloads one image URL, and "
        "validates whether it is safe for video generation. If prompt is present and non-empty, the image and "
        "generation prompt are judged together in one model call. It does not write PostgreSQL, ClickHouse, "
        "KVRocks, or storage state. The HMAC body hash must use the exact request bytes sent."
    ),
)
async def detect_image_url(
    request: ImageUrlDetectRequest,
    image_service: ImageServiceDep,
) -> ModerationDetectResponse:
    return await image_service.detect_url(request.image_url, prompt=request.prompt)


@router.post(
    "/detect-base64",
    response_model=ModerationDetectResponse,
    summary="Classify a base64 image",
    description=(
        "Protected stateless endpoint. Validates the two internal HMAC headers and validates whether one "
        "base64-encoded image is safe for video generation. If prompt is present and non-empty, the image and "
        "generation prompt are judged together in one model call. It does not write PostgreSQL, ClickHouse, "
        "KVRocks, or storage state. The HMAC body hash must use the exact request bytes sent."
    ),
)
async def detect_image_base64(
    request: ImageBase64DetectRequest,
    image_service: ImageServiceDep,
) -> ModerationDetectResponse:
    return await image_service.detect_base64(request.image_base64, prompt=request.prompt)
