import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.config.settings import Settings
from app.errors.video import (
    EmptyVideoDownloadError,
    NoVideoStreamError,
    VideoExtractionError,
    VideoProbeError,
    VideoTooLargeError,
)
from app.models.video_metadata import VideoMetadata
from app.utils.file_cleanup import cleanup_dir
from app.utils.subprocess import run_subprocess


@dataclass(frozen=True)
class ExtractedFrame:
    frame_index: int
    timestamp_seconds: float
    path: Path


async def download_video(
    source_url: str,
    output_path: Path,
    settings: Settings,
    http_client: httpx.AsyncClient | None = None,
) -> None:
    bytes_written = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    timeout = httpx.Timeout(settings.video_download_timeout_seconds)

    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=timeout, follow_redirects=True)
    try:
        async with client.stream("GET", source_url) as response:
            response.raise_for_status()
            with output_path.open("wb") as file:
                async for chunk in response.aiter_bytes():
                    bytes_written += len(chunk)
                    if bytes_written > settings.video_max_bytes:
                        raise VideoTooLargeError(bytes_written)
                    file.write(chunk)
    finally:
        if owns_client:
            await client.aclose()

    if bytes_written == 0:
        raise EmptyVideoDownloadError()


def job_temp_dir(job_id: str, settings: Settings) -> Path:
    safe_job_id = job_id.replace("/", "_")
    return Path(settings.video_temp_root) / safe_job_id


def frame_batches(frames: list[ExtractedFrame], batch_size: int = 5) -> list[list[ExtractedFrame]]:
    return [frames[index : index + batch_size] for index in range(0, len(frames), batch_size)]


def frames_from_paths(paths: Iterable[Path]) -> list[ExtractedFrame]:
    sorted_paths = sorted(paths)
    return [
        ExtractedFrame(frame_index=index, timestamp_seconds=float(index), path=path)
        for index, path in enumerate(sorted_paths)
    ]


class FrameExtractionService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def prepare_job_dir(self, job_id: str) -> Path:
        directory = job_temp_dir(job_id, self._settings)
        cleanup_dir(directory)
        (directory / "frames").mkdir(parents=True, exist_ok=True)
        return directory

    async def probe(self, *, job_id: str, video_id: str, source_path: Path) -> VideoMetadata:
        command = [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(source_path),
        ]
        try:
            result = await run_subprocess(command, timeout_seconds=self._settings.ffprobe_timeout_seconds)
        except TimeoutError as exc:
            raise VideoProbeError("ffprobe timed out") from exc
        except RuntimeError as exc:
            raise VideoProbeError(str(exc)) from exc

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise VideoProbeError("ffprobe returned invalid JSON") from exc
        return parse_ffprobe_metadata(job_id=job_id, video_id=video_id, payload=payload)

    async def extract_frames(self, source_path: Path, frames_dir: Path) -> list[ExtractedFrame]:
        frames_dir.mkdir(parents=True, exist_ok=True)
        output_pattern = frames_dir / "frame-%06d.jpg"
        command = [
            "ffmpeg",
            "-loglevel",
            "error",
            "-i",
            str(source_path),
            "-vf",
            "fps=1",
            "-q:v",
            "3",
            str(output_pattern),
        ]
        try:
            await run_subprocess(command, timeout_seconds=self._settings.ffmpeg_timeout_seconds)
        except TimeoutError as exc:
            raise VideoExtractionError("ffmpeg timed out") from exc
        except RuntimeError as exc:
            raise VideoExtractionError(str(exc)) from exc

        frames = frames_from_paths(frames_dir.glob("frame-*.jpg"))
        if not frames:
            raise VideoExtractionError("ffmpeg produced no frames")
        return frames


def parse_ffprobe_metadata(*, job_id: str, video_id: str, payload: dict[str, object]) -> VideoMetadata:
    streams = payload.get("streams")
    if not isinstance(streams, list):
        raise VideoProbeError("ffprobe response missing streams")

    video_stream = next(
        (stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "video"),
        None,
    )
    if video_stream is None:
        raise NoVideoStreamError()

    format_payload = payload.get("format") if isinstance(payload.get("format"), dict) else {}
    duration = _float_or_none(video_stream.get("duration")) or _float_or_none(format_payload.get("duration"))
    if duration is None:
        duration = 0.0

    return VideoMetadata(
        job_id=job_id,
        video_id=video_id,
        duration_seconds=duration,
        width=_int_or_none(video_stream.get("width")),
        height=_int_or_none(video_stream.get("height")),
        fps=_parse_rate(video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate")),
        codec_name=str(video_stream["codec_name"]) if video_stream.get("codec_name") else None,
        has_video_stream=True,
        frames_extracted=0,
    )


def _float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_rate(value: object) -> float | None:
    if not isinstance(value, str) or value in {"0/0", ""}:
        return None
    if "/" not in value:
        return _float_or_none(value)
    numerator, denominator = value.split("/", 1)
    denominator_float = _float_or_none(denominator)
    if not denominator_float:
        return None
    numerator_float = _float_or_none(numerator)
    if numerator_float is None:
        return None
    return numerator_float / denominator_float
