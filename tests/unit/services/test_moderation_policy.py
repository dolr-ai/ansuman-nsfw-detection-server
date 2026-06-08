from app.services.moderation_policy import compute_is_nsfw, compute_overall_severity


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


def test_compute_overall_severity_uses_top_category_score() -> None:
    assert compute_overall_severity("porn", categories(porn=4, gore=5)) == 4


def test_compute_is_nsfw_uses_category_thresholds() -> None:
    assert compute_is_nsfw(categories(porn=4)) is True
    assert compute_is_nsfw(categories(sexual_minor_content=3)) is True
    assert compute_is_nsfw(categories(gore=4)) is True
    assert compute_is_nsfw(categories(nudity=4, suggestive=4)) is False
    assert compute_is_nsfw(categories(nudity=5)) is True
    assert compute_is_nsfw(categories(safe=5)) is False
