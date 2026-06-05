from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_text_detection_service
from app.schemas.text import TextDetectRequest
from app.services.text_detection_service import TextDetectionService

router = APIRouter(prefix="/text", tags=["text"])
TextServiceDep = Annotated[TextDetectionService, Depends(get_text_detection_service)]


@router.post(
    "/detect",
    summary="Classify text prompt safety",
    description=(
        "Protected stateless endpoint. Validates the two internal HMAC headers, classifies a video-generation "
        "text prompt using the configured text moderation prompt, and returns the model verdict. "
        "It does not write PostgreSQL, ClickHouse, KVRocks, or storage state. The HMAC body hash must use the "
        "exact request bytes sent."
    ),
)
async def detect_text(
    request: TextDetectRequest,
    text_service: TextServiceDep,
) -> dict[str, object]:
    return await text_service.detect(request.text)
