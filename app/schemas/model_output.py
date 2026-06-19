import json

from pydantic import BaseModel, Field, ValidationError, computed_field, field_validator, model_validator

from app.core.constants import MODERATION_CATEGORIES
from app.errors import codes
from app.errors.base import AppError
from app.schemas.moderation import ModerationCategory, validate_category_scores
from app.services.moderation_policy import compute_is_nsfw, compute_overall_severity

UNSAFE_MODEL_CATEGORIES = tuple(category for category in MODERATION_CATEGORIES if category != "safe")


class ModerationModelOutput(BaseModel):
    top_category: ModerationCategory
    categories: dict[str, int]
    reason: str

    @field_validator("categories")
    @classmethod
    def validate_categories(cls, value: dict[str, int]) -> dict[str, int]:
        return validate_category_scores(value)

    @model_validator(mode="after")
    def top_category_matches_scores(self) -> "ModerationModelOutput":
        max_unsafe_severity = max(self.categories[category] for category in UNSAFE_MODEL_CATEGORIES)
        if self.top_category == "safe":
            if max_unsafe_severity != 0:
                raise ValueError("top_category safe requires all unsafe categories to be 0")
            return self
        top_category_severity = self.categories[self.top_category]
        if top_category_severity == 0:
            raise ValueError("top_category severity must be present for unsafe categories")
        if top_category_severity < max_unsafe_severity:
            raise ValueError("top_category must have the highest unsafe category severity")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def overall_severity(self) -> int:
        return compute_overall_severity(self.top_category, self.categories)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_nsfw(self) -> bool:
        return compute_is_nsfw(self.categories)


class FrameModerationOutput(ModerationModelOutput):
    frame_index: int = Field(ge=0)


class TextModerationOutput(ModerationModelOutput):
    pass


def parse_visual_batch_response(raw_response: str, expected_count: int) -> list[FrameModerationOutput]:
    try:
        payload = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise AppError(codes.MODEL_RESPONSE_INVALID_JSON, "model response was not valid JSON", status_code=502) from exc

    if not isinstance(payload, list):
        raise AppError(codes.MODEL_RESPONSE_INVALID_SCHEMA, "model response must be a JSON array", status_code=502)
    if len(payload) != expected_count:
        raise AppError(
            codes.MODEL_RESPONSE_INVALID_SCHEMA,
            "model response count did not match request count",
            status_code=502,
        )

    results: list[FrameModerationOutput] = []
    for index, item in enumerate(payload):
        try:
            parsed = FrameModerationOutput.model_validate(item)
        except ValidationError as exc:
            raise AppError(
                codes.MODEL_RESPONSE_INVALID_SCHEMA,
                f"invalid frame response at index {index}",
                status_code=502,
            ) from exc
        if parsed.frame_index != index:
            raise AppError(
                codes.MODEL_RESPONSE_INVALID_SCHEMA,
                "frame_index did not match response order",
                status_code=502,
            )
        results.append(parsed)
    return results


def parse_text_moderation_response(raw_response: str) -> TextModerationOutput:
    try:
        payload = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise AppError(codes.MODEL_RESPONSE_INVALID_JSON, "model response was not valid JSON", status_code=502) from exc

    if not isinstance(payload, dict):
        raise AppError(
            codes.MODEL_RESPONSE_INVALID_SCHEMA,
            "text model response must be a JSON object",
            status_code=502,
        )

    try:
        return TextModerationOutput.model_validate(payload)
    except ValidationError as exc:
        raise AppError(
            codes.MODEL_RESPONSE_INVALID_SCHEMA,
            "invalid text moderation response",
            status_code=502,
        ) from exc
