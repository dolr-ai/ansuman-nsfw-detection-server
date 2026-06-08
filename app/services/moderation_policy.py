from collections.abc import Mapping

from app.core.constants import MODERATION_CATEGORIES

CATEGORY_BLOCK_THRESHOLDS: dict[str, int] = {
    "porn": 4,
    "sexual_minor_content": 3,
    "gore": 4,
    "violence": 4,
    "self_harm": 4,
    "hate_or_extremism": 4,
    "drugs": 4,
    "unknown": 4,
    "suggestive": 5,
    "nudity": 5,
}


def compute_overall_severity(top_category: str, categories: Mapping[str, int]) -> int:
    if top_category not in MODERATION_CATEGORIES:
        raise ValueError(f"unknown moderation category: {top_category}")
    return int(categories[top_category])


def compute_is_nsfw(categories: Mapping[str, int]) -> bool:
    return any(
        int(categories.get(category, 0)) >= threshold
        for category, threshold in CATEGORY_BLOCK_THRESHOLDS.items()
    )
