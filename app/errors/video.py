from app.errors import codes
from app.errors.base import AppError


class EmptyVideoDownloadError(AppError):
    def __init__(self) -> None:
        super().__init__(codes.VIDEO_DOWNLOAD_EMPTY, "video download returned no bytes")


class VideoTooLargeError(AppError):
    def __init__(self, bytes_written: int) -> None:
        super().__init__(codes.VIDEO_TOO_LARGE, f"video exceeded max size after {bytes_written} bytes")


class NoVideoStreamError(AppError):
    def __init__(self) -> None:
        super().__init__(codes.VIDEO_NO_STREAM, "video has no usable video stream")


class VideoProbeError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(codes.VIDEO_PROBE_FAILED, message)


class VideoExtractionError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(codes.VIDEO_EXTRACTION_FAILED, message)
