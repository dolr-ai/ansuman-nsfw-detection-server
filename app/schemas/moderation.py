from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.constants import MODERATION_CATEGORIES
from app.services.moderation_policy import compute_is_nsfw, compute_overall_severity

ModerationCategory = Literal[
    "safe",
    "suggestive",
    "nudity",
    "porn",
    "gore",
    "violence",
    "self_harm",
    "hate_or_extremism",
    "drugs",
    "unknown",
    "sexual_minor_content",
]


def validate_category_scores(value: dict[str, int]) -> dict[str, int]:
    expected = set(MODERATION_CATEGORIES)
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ValueError(f"categories mismatch missing={missing} extra={extra}")
    for category, severity in value.items():
        if isinstance(severity, bool) or not isinstance(severity, int) or severity < 0 or severity > 5:
            raise ValueError(f"{category} severity must be an integer between 0 and 5")
    return value


class ModerationDetectResponse(BaseModel):
    top_category: ModerationCategory
    is_nsfw: bool
    overall_severity: int = Field(ge=0, le=5)
    categories: dict[str, int]
    reason: str

    @field_validator("categories")
    @classmethod
    def validate_categories(cls, value: dict[str, int]) -> dict[str, int]:
        return validate_category_scores(value)

    @model_validator(mode="after")
    def validate_policy_fields(self) -> "ModerationDetectResponse":
        expected_overall_severity = compute_overall_severity(self.top_category, self.categories)
        if self.overall_severity != expected_overall_severity:
            raise ValueError("overall_severity must equal categories[top_category]")
        expected_is_nsfw = compute_is_nsfw(self.categories)
        if self.is_nsfw != expected_is_nsfw:
            raise ValueError("is_nsfw must match moderation policy thresholds")
        return self
