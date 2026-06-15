from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import get_manual_ban_service, get_queue_service, get_video_status_service
from app.errors.base import AppError
from app.errors.codes import NOT_FOUND
from app.schemas.video import (
    VideoBanRequest,
    VideoBanResponse,
    VideoDetectRequest,
    VideoDetectResponse,
    VideoStatusResponse,
)
from app.services.manual_ban_service import ManualBanService
from app.services.queue_service import QueueService
from app.services.video_status_service import VideoStatusService

router = APIRouter(prefix="/videos", tags=["videos"])
QueueServiceDep = Annotated[QueueService, Depends(get_queue_service)]
VideoStatusServiceDep = Annotated[VideoStatusService, Depends(get_video_status_service)]
ManualBanServiceDep = Annotated[ManualBanService, Depends(get_manual_ban_service)]


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
    video_status_service: VideoStatusServiceDep,
) -> VideoStatusResponse:
    response = await video_status_service.get_status_by_video_id(video_id)
    if response is None:
        raise AppError(NOT_FOUND, "video job not found", status_code=404)
    return response


@router.post(
    "/{video_id}/ban",
    response_model=VideoBanResponse,
    summary="Record a manual video ban",
    description=(
        "Protected internal endpoint for human-approved moderation bans. "
        "It does not enqueue NSFW processing or write classifier rows. "
        "It synchronously writes `excluded_videos` and the legacy `video_nsfw_agg` compatibility row.\n\n"
        "Sign `<timestamp>\\nPOST\\n/v1/videos/{video_id}/ban\\n<SHA256(raw JSON body)>` with HMAC-SHA256."
    ),
)
async def ban_video(
    video_id: str,
    request: VideoBanRequest,
    manual_ban_service: ManualBanServiceDep,
) -> VideoBanResponse:
    result = await manual_ban_service.ban_video(video_id, request)
    return VideoBanResponse(
        video_id=result.video_id,
        status=result.status,
        excluded_videos_written=result.excluded_videos_written,
        legacy_nsfw_agg_written=result.legacy_nsfw_agg_written,
        trace_id=result.trace_id,
    )
