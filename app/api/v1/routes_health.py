from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import get_readiness_service
from app.schemas.common import ReadinessResponse
from app.services.readiness_service import ReadinessService

router = APIRouter(tags=["health"])
ReadinessDep = Annotated[ReadinessService, Depends(get_readiness_service)]


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", response_model=ReadinessResponse)
async def ready(
    response: Response,
    readiness_service: ReadinessDep,
) -> ReadinessResponse:
    dependencies = await readiness_service.check()
    is_ready = all(bool(item["ready"]) for item in dependencies)
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ready" if is_ready else "not_ready",
        dependencies=dependencies,
    )
