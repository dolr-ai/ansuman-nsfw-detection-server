from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import get_queue_service
from app.errors.base import AppError
from app.errors.codes import NOT_FOUND
from app.schemas.video import VideoDetectRequest, VideoDetectResponse, VideoStatusResponse
from app.services.queue_service import QueueService

router = APIRouter(prefix="/videos", tags=["videos"])
QueueServiceDep = Annotated[QueueService, Depends(get_queue_service)]


@router.post(
    "/detect",
    response_model=VideoDetectResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Enqueue video NSFW detection",
    description=(
        "Protected internal endpoint. Validates `X-Internal-Timestamp` and `X-Internal-Signature`, "
        "stores the video job in the durable queue, "
        "and returns `202 Accepted`. Classification happens asynchronously in workers.\n\n"
        "Sign `<timestamp>\\nPOST\\n/v1/videos/detect\\n<SHA256(raw JSON body)>` with HMAC-SHA256. "
        "The body hash must use the exact request bytes sent."
    ),
)
async def detect_video(
    request: VideoDetectRequest,
    queue_service: QueueServiceDep,
) -> VideoDetectResponse:
    result = await queue_service.enqueue_video_detection(request)
    return VideoDetectResponse(
        job_id=result.job.job_id,
        video_id=result.job.video_id,
        status=result.job.status,
        trace_id=result.job.trace_id,
    )


@router.get(
    "/{video_id}/status",
    response_model=VideoStatusResponse,
    summary="Get video detection status",
    description=(
        "Protected internal endpoint. Returns the latest known queue/classification state for a video.\n\n"
        "Sign `<timestamp>\\nGET\\n/v1/videos/{video_id}/status\\n<SHA256(empty body)>` with HMAC-SHA256."
    ),
)
async def video_status(
    video_id: str,
    queue_service: QueueServiceDep,
) -> VideoStatusResponse:
    job = await queue_service.get_status_by_video_id(video_id)
    if job is None:
        raise AppError(NOT_FOUND, "video job not found", status_code=404)
    return VideoStatusResponse(
        job_id=job.job_id,
        video_id=job.video_id,
        status=job.status,
        trace_id=job.trace_id,
        attempts=job.attempts,
        last_error_code=job.last_error_code,
        last_error_message=job.last_error_message,
        final_result=None,
    )
