from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import VideoJobStatus


class VideoDetectRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "job_id": "nsfw:video-id:nsfw_policy_v1:",
                    "video_id": "video-id",
                    "publisher_user_id": "principal-or-user-id",
                    "source_video_uri": "https://link.storjshare.io/raw/bucket/path/video.mp4",
                    "post_id": "post-id-or-null",
                    "canister_id": "canister-id-or-null",
                    "source_object_version": "",
                    "upload_event_id": "event-id-or-null",
                    "upload_created_at": "2026-06-05T00:00:00Z",
                    "policy_version": "nsfw_policy_v1",
                    "trace_id": "trace-id",
                }
            ]
        }
    )

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
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "job_id": "nsfw:video-id:nsfw_policy_v1:",
                    "video_id": "video-id",
                    "status": "queued",
                    "trace_id": "trace-id",
                }
            ]
        }
    )

    job_id: str
    video_id: str
    status: VideoJobStatus
    trace_id: str | None = None


class VideoFinalResultResponse(BaseModel):
    policy_version: str
    prompt_version: str
    aggregation_version: str
    final_is_nsfw: bool
    final_score: float
    final_top_category: str
    max_overall_severity: int
    nsfw_frame_count: int
    total_frame_count: int
    move_required: bool
    move_threshold: float
    max_category_severities: dict[str, int]
    legacy_nsfw_ec: str
    legacy_nsfw_gore: str
    final_response: dict[str, object]


class VideoStatusResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "job_id": "nsfw:video-id:nsfw_policy_v1:",
                    "video_id": "video-id",
                    "status": "classified",
                    "trace_id": "trace-id",
                    "attempts": 1,
                    "last_error_code": None,
                    "last_error_message": None,
                    "final_result": {
                        "policy_version": "nsfw_policy_v1",
                        "prompt_version": "visual_batch_moderation_v1",
                        "aggregation_version": "hard_any_frame_v1",
                        "final_is_nsfw": False,
                        "final_score": 0.0,
                        "final_top_category": "safe",
                        "max_overall_severity": 0,
                        "nsfw_frame_count": 0,
                        "total_frame_count": 5,
                        "move_required": False,
                        "move_threshold": 0.8,
                        "max_category_severities": {"safe": 0},
                        "legacy_nsfw_ec": "neutral",
                        "legacy_nsfw_gore": "VERY_UNLIKELY",
                        "final_response": {"final_is_nsfw": False},
                    },
                }
            ]
        }
    )

    job_id: str
    video_id: str
    status: VideoJobStatus
    trace_id: str | None = None
    attempts: int = 0
    last_error_code: str | None = None
    last_error_message: str | None = None
    final_result: VideoFinalResultResponse | None = None


class VideoBanRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "publisher_user_id": "principal-or-user-id",
                    "post_id": "post-id",
                    "canister_id": "canister-id",
                    "reason": "user_report_approved",
                    "source": "google_chat",
                    "moderator_id": None,
                    "trace_id": "report-approved:canister-id:post-id",
                }
            ]
        }
    )

    publisher_user_id: str = Field(min_length=1)
    post_id: str = Field(min_length=1)
    canister_id: str = Field(min_length=1)
    reason: str = Field(default="user_report_approved", min_length=1)
    source: str = Field(default="google_chat", min_length=1)
    moderator_id: str | None = None
    trace_id: str | None = None


class VideoBanResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "video_id": "video-id",
                    "status": "banned",
                    "excluded_videos_written": True,
                    "legacy_nsfw_agg_written": True,
                    "trace_id": "report-approved:canister-id:post-id",
                }
            ]
        }
    )

    video_id: str
    status: str
    excluded_videos_written: bool
    legacy_nsfw_agg_written: bool
    trace_id: str | None = None
