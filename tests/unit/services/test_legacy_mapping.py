from datetime import UTC, datetime

from app.models.video_result import VideoModerationResult
from app.services.legacy_mapping_service import map_legacy_nsfw_ec, map_legacy_nsfw_gore, to_legacy_nsfw_agg


def test_legacy_nsfw_ec_mapping() -> None:
    assert map_legacy_nsfw_ec("porn") == "explicit"
    assert map_legacy_nsfw_ec("nudity") == "nudity"
    assert map_legacy_nsfw_ec("suggestive") == "provocative"
    assert map_legacy_nsfw_ec("safe") == "neutral"


def test_legacy_gore_mapping() -> None:
    assert map_legacy_nsfw_gore({"gore": 5, "violence": 0}) == "VERY_LIKELY"
    assert map_legacy_nsfw_gore({"gore": 4, "violence": 0}) == "LIKELY"
    assert map_legacy_nsfw_gore({"gore": 3, "violence": 0}) == "POSSIBLE"
    assert map_legacy_nsfw_gore({"gore": 1, "violence": 0}) == "UNLIKELY"
    assert map_legacy_nsfw_gore({"gore": 0, "violence": 0}) == "VERY_UNLIKELY"


def test_to_legacy_nsfw_agg_row() -> None:
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
        total_frame_count=2,
        move_required=True,
        move_threshold=0.8,
        max_category_severities={"gore": 0, "violence": 0},
        legacy_nsfw_ec="explicit",
        legacy_nsfw_gore="VERY_UNLIKELY",
        final_response={},
        created_at=now,
        updated_at=now,
    )

    legacy = to_legacy_nsfw_agg(result)

    assert legacy.video_id == "video"
    assert legacy.gcs_video_id is None
    assert legacy.nsfw_ec == "explicit"
    assert legacy.is_nsfw is True
    assert legacy.probability == 0.8

