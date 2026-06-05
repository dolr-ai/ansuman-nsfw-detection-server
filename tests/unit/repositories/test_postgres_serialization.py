from datetime import UTC, datetime

from app.core.constants import VideoJobStatus
from app.models.frame_result import FrameModerationResult
from app.models.storage_action import StorageAction
from app.models.video_job import VideoJob
from app.models.video_result import VideoModerationResult
from app.repositories.postgres.frame_result_repository import frame_result_to_row
from app.repositories.postgres.storage_action_repository import storage_action_to_row
from app.repositories.postgres.video_job_repository import video_job_to_row
from app.repositories.postgres.video_result_repository import video_result_to_row


def categories(**overrides: int) -> dict[str, int]:
    base = {
        "safe": 0,
        "suggestive": 0,
        "nudity": 0,
        "porn": 0,
        "gore": 0,
        "violence": 0,
        "self_harm": 0,
        "hate_or_extremism": 0,
        "drugs": 0,
        "unknown": 0,
        "sexual_minor_content": 0,
    }
    base.update(overrides)
    return base


def test_video_job_serializes_status_value() -> None:
    row = video_job_to_row(
        VideoJob(
            job_id="job",
            video_id="video",
            source_object_version="",
            policy_version="nsfw_policy_v1",
            status=VideoJobStatus.QUEUED,
            publisher_user_id="user",
            post_id=None,
            canister_id=None,
            source_video_uri="https://example.com/video.mp4",
            upload_event_id=None,
            trace_id="trace",
        )
    )

    assert row["status"] == "queued"
    assert row["job_id"] == "job"


def test_frame_result_serializes_category_columns() -> None:
    frame = FrameModerationResult(
        frame_index=3,
        frame_timestamp_seconds=3.0,
        top_category="porn",
        is_nsfw=True,
        overall_severity=4,
        categories=categories(porn=4),
        reason="fixture",
        raw_response={"frame_index": 3},
    )

    row = frame_result_to_row(
        job_id="job",
        video_id="video",
        prompt_version="visual_batch_moderation_v1",
        model_provider="openai-compatible",
        model_name="model",
        model_version=None,
        frame=frame,
    )

    assert row["frame_id"] == "job:3"
    assert row["porn_severity"] == 4
    assert row["overall_severity"] == 4


def test_video_result_serializes_final_result() -> None:
    now = datetime.now(UTC)
    result = VideoModerationResult(
        job_id="job",
        video_id="video",
        policy_version="nsfw_policy_v1",
        prompt_version="visual_batch_moderation_v1",
        aggregation_version="hard_any_frame_v1",
        final_is_nsfw=True,
        final_score=0.8,
        final_top_category="porn",
        max_overall_severity=4,
        nsfw_frame_count=1,
        total_frame_count=5,
        move_required=True,
        move_threshold=0.8,
        max_category_severities=categories(porn=4),
        legacy_nsfw_ec="explicit",
        legacy_nsfw_gore="VERY_UNLIKELY",
        final_response={"final_is_nsfw": True},
        created_at=now,
        updated_at=now,
    )

    row = video_result_to_row(result)

    assert row["legacy_nsfw_ec"] == "explicit"
    assert row["move_required"] is True


def test_storage_action_serializes_request_and_response() -> None:
    now = datetime.now(UTC)
    row = storage_action_to_row(
        StorageAction(
            action_id="action",
            job_id="job",
            video_id="video",
            publisher_user_id="user",
            action_type="move_to_nsfw",
            threshold=0.8,
            final_score=0.8,
            request_url="https://storj/move-to-nsfw",
            request_body={"video_id": "video"},
            response_status=200,
            response_body="ok",
            status="succeeded",
            created_at=now,
            completed_at=now,
        )
    )

    assert row["request_body"] == {"video_id": "video"}
    assert row["response_status"] == 200

