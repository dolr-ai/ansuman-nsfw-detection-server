import json

from pydantic import BaseModel, Field, ValidationError, computed_field, field_validator, model_validator

from app.core.constants import MODERATION_CATEGORIES
from app.errors import codes
from app.errors.base import AppError
from app.schemas.moderation import ModerationCategory, validate_category_scores
from app.services.moderation_policy import compute_is_nsfw, compute_overall_severity

UNSAFE_MODEL_CATEGORIES = tuple(category for category in MODERATION_CATEGORIES if category != "safe")
_MISSING_JSON = object()


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


def _load_model_json(raw_response: str) -> object:
    candidate = raw_response.lstrip("\ufeff").strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        extracted = _extract_single_json_document(candidate)
        if extracted is _MISSING_JSON:
            raise AppError(
                codes.MODEL_RESPONSE_INVALID_JSON,
                "model response was not valid JSON",
                status_code=502,
            ) from exc
        return extracted


def _extract_single_json_document(raw_response: str) -> object:
    start = _next_json_start(raw_response, 0)
    if start is None:
        return _MISSING_JSON

    decoder = json.JSONDecoder()
    try:
        payload, end = decoder.raw_decode(raw_response, start)
    except json.JSONDecodeError:
        return _MISSING_JSON
    if not isinstance(payload, (dict, list)):
        return _MISSING_JSON

    cursor = end
    while (next_start := _next_json_start(raw_response, cursor)) is not None:
        try:
            extra_payload, extra_end = decoder.raw_decode(raw_response, next_start)
        except json.JSONDecodeError:
            cursor = next_start + 1
            continue
        if isinstance(extra_payload, (dict, list)):
            return _MISSING_JSON
        cursor = extra_end
    return payload


def _next_json_start(value: str, start: int) -> int | None:
    positions = [position for token in ("{", "[") if (position := value.find(token, start)) >= 0]
    return min(positions) if positions else None


def _unwrap_envelope(payload: object, keys: tuple[str, ...]) -> object:
    if not isinstance(payload, dict) or len(payload) != 1:
        return payload
    key = next(iter(payload))
    return payload[key] if key in keys else payload


def parse_visual_batch_response(raw_response: str, expected_count: int) -> list[FrameModerationOutput]:
    payload = _load_model_json(raw_response)
    payload = _unwrap_envelope(payload, ("results", "frames", "result"))
    if isinstance(payload, dict) and expected_count == 1 and "frame_index" in payload:
        payload = [payload]

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
    payload = _load_model_json(raw_response)
    payload = _unwrap_envelope(payload, ("result", "moderation"))

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
