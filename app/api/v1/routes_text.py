from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_text_detection_service
from app.schemas.text import TextDetectRequest
from app.services.text_detection_service import TextDetectionService

router = APIRouter(prefix="/text", tags=["text"])
TextServiceDep = Annotated[TextDetectionService, Depends(get_text_detection_service)]


@router.post("/detect")
async def detect_text(
    request: TextDetectRequest,
    text_service: TextServiceDep,
) -> dict[str, object]:
    return await text_service.detect(request.text)
