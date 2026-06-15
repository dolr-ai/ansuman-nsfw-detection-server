from typing import Annotated

from fastapi import APIRouter, Depends, status
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import MaxConnectionsError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.api.deps import get_queue_service, get_video_status_service
from app.errors.base import AppError
from app.errors.codes import NOT_FOUND, QUEUE_UNAVAILABLE
from app.schemas.video import VideoDetectRequest, VideoDetectResponse, VideoStatusResponse
from app.services.queue_service import QueueService
from app.services.video_status_service import VideoStatusService

router = APIRouter(prefix="/videos", tags=["videos"])
QueueServiceDep = Annotated[QueueService, Depends(get_queue_service)]
VideoStatusServiceDep = Annotated[VideoStatusService, Depends(get_video_status_service)]
QUEUE_UNAVAILABLE_MESSAGE = "queue storage is temporarily unavailable"


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
    try:
        result = await queue_service.enqueue_video_detection(request)
    except (MaxConnectionsError, RedisConnectionError, RedisTimeoutError) as exc:
        raise _queue_unavailable_error() from exc
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
    video_status_service: VideoStatusServiceDep,
) -> VideoStatusResponse:
    try:
        response = await video_status_service.get_status_by_video_id(video_id)
    except (MaxConnectionsError, RedisConnectionError, RedisTimeoutError) as exc:
        raise _queue_unavailable_error() from exc
    if response is None:
        raise AppError(NOT_FOUND, "video job not found", status_code=404)
    return response


def _queue_unavailable_error() -> AppError:
    return AppError(
        QUEUE_UNAVAILABLE,
        QUEUE_UNAVAILABLE_MESSAGE,
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    )
