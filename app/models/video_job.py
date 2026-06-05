from dataclasses import dataclass
from datetime import datetime

from app.core.constants import VideoJobStatus


@dataclass(frozen=True)
class VideoJob:
    job_id: str
    video_id: str
    source_object_version: str
    policy_version: str
    status: VideoJobStatus
    publisher_user_id: str
    post_id: str | None
    canister_id: str | None
    source_video_uri: str
    upload_event_id: str | None
    trace_id: str | None
    attempts: int = 0
    last_error_code: str | None = None
    last_error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

