from app.errors.base import AppError
from app.schemas.moderation import ModerationDetectResponse
from app.services.gpu_moderation_service import GpuModerationService
from app.services.moderation_policy import compute_is_nsfw, compute_overall_severity


class TextDetectionService:
    def __init__(self, *, gpu_service: GpuModerationService | None = None) -> None:
        self._gpu_service = gpu_service

    async def detect(self, text: str) -> ModerationDetectResponse:
        if self._gpu_service is None:
            raise AppError("gpu_not_configured", "GPU moderation is not configured", status_code=503)
        result = await self._gpu_service.moderate_text(text)
        return ModerationDetectResponse(
            top_category=result.top_category,
            is_nsfw=compute_is_nsfw(result.categories),
            overall_severity=compute_overall_severity(result.top_category, result.categories),
            categories=result.categories,
            reason=result.reason,
        )
