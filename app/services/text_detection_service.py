from app.errors.base import AppError
from app.services.gpu_moderation_service import GpuModerationService


class TextDetectionService:
    def __init__(self, *, gpu_service: GpuModerationService | None = None) -> None:
        self._gpu_service = gpu_service

    async def detect(self, text: str) -> dict[str, object]:
        if self._gpu_service is None:
            raise AppError("gpu_not_configured", "GPU moderation is not configured", status_code=503)
        result = await self._gpu_service.moderate_text(text)
        return result.model_dump(mode="json")
