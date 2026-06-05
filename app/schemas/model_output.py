import json
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from app.core.constants import MODERATION_CATEGORIES
from app.errors.base import AppError
from app.errors.codes import VALIDATION_ERROR

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


class FrameModerationOutput(BaseModel):
    frame_index: int = Field(ge=0)
    top_category: ModerationCategory
    is_nsfw: bool
    overall_severity: int = Field(ge=0, le=5)
    categories: dict[str, int]
    reason: str

    @field_validator("categories")
    @classmethod
    def validate_categories(cls, value: dict[str, int]) -> dict[str, int]:
        expected = set(MODERATION_CATEGORIES)
        actual = set(value)
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            raise ValueError(f"categories mismatch missing={missing} extra={extra}")
        for category, severity in value.items():
            if not isinstance(severity, int) or severity < 0 or severity > 5:
                raise ValueError(f"{category} severity must be an integer between 0 and 5")
        return value

    @model_validator(mode="after")
    def top_category_has_score(self) -> "FrameModerationOutput":
        if self.top_category != "safe" and self.categories[self.top_category] == 0:
            raise ValueError("top_category severity must be present for unsafe categories")
        return self


class TextModerationOutput(BaseModel):
    top_category: ModerationCategory
    is_nsfw: bool
    should_block: bool
    overall_severity: int = Field(ge=0, le=5)
    categories: dict[str, int]
    reason: str

    @field_validator("categories")
    @classmethod
    def validate_categories(cls, value: dict[str, int]) -> dict[str, int]:
        return FrameModerationOutput.validate_categories(value)

    @model_validator(mode="after")
    def validate_blocking_rules(self) -> "TextModerationOutput":
        if self.top_category == "sexual_minor_content":
            if not self.should_block or self.overall_severity != 5:
                raise ValueError("sexual_minor_content must block with severity 5")
        elif self.should_block != (self.overall_severity >= 4):
            raise ValueError("should_block must match overall_severity >= 4")
        if self.top_category != "safe" and self.categories[self.top_category] == 0:
            raise ValueError("top_category severity must be present for unsafe categories")
        return self


def parse_visual_batch_response(raw_response: str, expected_count: int) -> list[FrameModerationOutput]:
    try:
        payload = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise AppError(VALIDATION_ERROR, "model response was not valid JSON") from exc

    if not isinstance(payload, list):
        raise AppError(VALIDATION_ERROR, "model response must be a JSON array")
    if len(payload) != expected_count:
        raise AppError(VALIDATION_ERROR, "model response count did not match request count")

    results: list[FrameModerationOutput] = []
    for index, item in enumerate(payload):
        try:
            parsed = FrameModerationOutput.model_validate(item)
        except ValidationError as exc:
            raise AppError(VALIDATION_ERROR, f"invalid frame response at index {index}") from exc
        if parsed.frame_index != index:
            raise AppError(VALIDATION_ERROR, "frame_index did not match response order")
        results.append(parsed)
    return results


def parse_text_moderation_response(raw_response: str) -> TextModerationOutput:
    try:
        payload = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise AppError(VALIDATION_ERROR, "model response was not valid JSON") from exc

    if not isinstance(payload, dict):
        raise AppError(VALIDATION_ERROR, "text model response must be a JSON object")

    try:
        return TextModerationOutput.model_validate(payload)
    except ValidationError as exc:
        raise AppError(VALIDATION_ERROR, "invalid text moderation response") from exc
