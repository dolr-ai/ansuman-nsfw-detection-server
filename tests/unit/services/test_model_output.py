import json

import pytest

from app.errors.base import AppError
from app.schemas.model_output import parse_text_moderation_response, parse_visual_batch_response


def frame(index: int, *, top_category: str = "safe", is_nsfw: bool = False, severity: int = 0) -> dict[str, object]:
    categories = {
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
    categories[top_category] = severity
    return {
        "frame_index": index,
        "top_category": top_category,
        "is_nsfw": is_nsfw,
        "overall_severity": severity,
        "categories": categories,
        "reason": "fixture",
    }


def test_parse_valid_five_frame_response() -> None:
    raw = json.dumps([frame(index) for index in range(5)])

    parsed = parse_visual_batch_response(raw, expected_count=5)

    assert [item.frame_index for item in parsed] == [0, 1, 2, 3, 4]


def test_rejects_non_json() -> None:
    with pytest.raises(AppError):
        parse_visual_batch_response("not-json", expected_count=1)


def test_rejects_wrong_count() -> None:
    with pytest.raises(AppError):
        parse_visual_batch_response(json.dumps([frame(0)]), expected_count=2)


def test_rejects_out_of_range_severity() -> None:
    payload = [frame(0, top_category="porn", is_nsfw=True, severity=6)]

    with pytest.raises(AppError):
        parse_visual_batch_response(json.dumps(payload), expected_count=1)


def text_payload(*, top_category: str = "safe", severity: int = 0, should_block: bool = False) -> dict[str, object]:
    payload = frame(0, top_category=top_category, is_nsfw=should_block, severity=severity)
    payload.pop("frame_index")
    payload["should_block"] = should_block
    return payload


def test_parse_text_moderation_response_accepts_prompt_shape() -> None:
    parsed = parse_text_moderation_response(
        json.dumps(text_payload(top_category="porn", severity=4, should_block=True))
    )

    assert parsed.top_category == "porn"
    assert parsed.should_block is True


def test_parse_text_moderation_response_rejects_blocking_rule_mismatch() -> None:
    with pytest.raises(AppError):
        parse_text_moderation_response(json.dumps(text_payload(top_category="violence", severity=3, should_block=True)))


def test_parse_text_moderation_response_requires_sexual_minor_block() -> None:
    with pytest.raises(AppError):
        parse_text_moderation_response(
            json.dumps(text_payload(top_category="sexual_minor_content", severity=4, should_block=True))
        )
