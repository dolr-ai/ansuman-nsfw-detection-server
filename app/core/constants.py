from enum import StrEnum


class VideoJobStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    CLASSIFIED = "classified"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_TERMINAL = "failed_terminal"
    SUPERSEDED = "superseded"


TERMINAL_VIDEO_STATUSES = {
    VideoJobStatus.CLASSIFIED,
    VideoJobStatus.FAILED_TERMINAL,
    VideoJobStatus.SUPERSEDED,
}

MODERATION_CATEGORIES = (
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
)

UNSAFE_CATEGORIES = {
    "suggestive",
    "nudity",
    "porn",
    "gore",
    "violence",
    "self_harm",
    "hate_or_extremism",
    "drugs",
    "sexual_minor_content",
}

RISK_ORDER = (
    "sexual_minor_content",
    "porn",
    "nudity",
    "gore",
    "violence",
    "self_harm",
    "hate_or_extremism",
    "drugs",
    "suggestive",
    "unknown",
    "safe",
)

