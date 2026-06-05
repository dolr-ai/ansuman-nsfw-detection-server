from datetime import datetime

from pydantic import BaseModel, Field

from app.core.constants import VideoJobStatus


class VideoDetectRequest(BaseModel):
    job_id: str = Field(min_length=1)
    video_id: str = Field(min_length=1)
    publisher_user_id: str = Field(min_length=1)
    source_video_uri: str = Field(min_length=1)
    post_id: str | None = None
    canister_id: str | None = None
    source_object_version: str = ""
    upload_event_id: str | None = None
    upload_created_at: datetime | None = None
    policy_version: str = Field(default="nsfw_policy_v1", min_length=1)
    trace_id: str | None = None


class VideoDetectResponse(BaseModel):
    job_id: str
    video_id: str
    status: VideoJobStatus
    trace_id: str | None = None


class VideoStatusResponse(BaseModel):
    job_id: str
    video_id: str
    status: VideoJobStatus
    trace_id: str | None = None
    attempts: int = 0
    last_error_code: str | None = None
    last_error_message: str | None = None
    final_result: dict[str, object] | None = None

