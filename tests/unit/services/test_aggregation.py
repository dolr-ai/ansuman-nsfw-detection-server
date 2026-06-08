from app.models.frame_result import FrameModerationResult
from app.services.aggregation_service import AggregationService


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


def result(index: int, top: str, severity: int, is_nsfw: bool = False) -> FrameModerationResult:
    return FrameModerationResult(
        frame_index=index,
        frame_timestamp_seconds=float(index),
        top_category=top,
        is_nsfw=is_nsfw,
        overall_severity=severity,
        categories=categories(**{top: severity}),
        reason="fixture",
        raw_response={},
    )


def test_all_safe_frames_are_clean(test_settings) -> None:  # type: ignore[no-untyped-def]
    service = AggregationService(test_settings)

    final = service.aggregate(
        job_id="job",
        video_id="video",
        policy_version="nsfw_policy_v1",
        frames=[result(0, "safe", 0)],
    )

    assert final.final_is_nsfw is False
    assert final.final_score == 0.0
    assert final.move_required is False


def test_one_nsfw_frame_flags_video(test_settings) -> None:  # type: ignore[no-untyped-def]
    service = AggregationService(test_settings)

    final = service.aggregate(
        job_id="job",
        video_id="video",
        policy_version="nsfw_policy_v1",
        frames=[result(0, "safe", 0), result(1, "porn", 4, is_nsfw=True)],
    )

    assert final.final_is_nsfw is True
    assert final.final_score == 0.8
    assert final.move_required is True
    assert final.final_top_category == "porn"


def test_low_severity_unsafe_category_does_not_flag_without_policy_boolean(test_settings) -> None:  # type: ignore[no-untyped-def]
    service = AggregationService(test_settings)

    final = service.aggregate(
        job_id="job",
        video_id="video",
        policy_version="nsfw_policy_v1",
        frames=[result(0, "suggestive", 3, is_nsfw=False)],
    )

    assert final.final_is_nsfw is False
    assert final.nsfw_frame_count == 0
    assert final.final_score == 0.6


def test_risk_tiebreak_prefers_sexual_minor_content(test_settings) -> None:  # type: ignore[no-untyped-def]
    service = AggregationService(test_settings)

    final = service.aggregate(
        job_id="job",
        video_id="video",
        policy_version="nsfw_policy_v1",
        frames=[
            result(0, "porn", 5, is_nsfw=True),
            result(1, "sexual_minor_content", 5, is_nsfw=True),
        ],
    )

    assert final.final_top_category == "sexual_minor_content"
