from pathlib import Path

import httpx
import pytest

from app.errors.video import EmptyVideoDownloadError, NoVideoStreamError, VideoTooLargeError
from app.services.frame_extraction_service import (
    ExtractedFrame,
    download_video,
    frame_batches,
    frames_from_paths,
    parse_ffprobe_metadata,
)


@pytest.mark.asyncio
async def test_download_video_streams_to_disk(test_settings, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"video-bytes")

    output_path = tmp_path / "source.mp4"
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await download_video("https://example.com/video.mp4?token=secret", output_path, test_settings, client)

    assert output_path.read_bytes() == b"video-bytes"


@pytest.mark.asyncio
async def test_download_video_rejects_empty_body(test_settings, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(EmptyVideoDownloadError):
            await download_video("https://example.com/video.mp4", tmp_path / "source.mp4", test_settings, client)


@pytest.mark.asyncio
async def test_download_video_enforces_max_bytes(test_settings, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    settings = test_settings.model_copy(update={"video_max_bytes": 4})

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"too-large")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(VideoTooLargeError):
            await download_video("https://example.com/video.mp4", tmp_path / "source.mp4", settings, client)


def test_parse_ffprobe_metadata_extracts_video_fields() -> None:
    metadata = parse_ffprobe_metadata(
        job_id="job",
        video_id="video",
        payload={
            "format": {"duration": "2.4"},
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 320,
                    "height": 180,
                    "avg_frame_rate": "30/1",
                }
            ],
        },
    )

    assert metadata.duration_seconds == 2.4
    assert metadata.width == 320
    assert metadata.height == 180
    assert metadata.fps == 30.0
    assert metadata.codec_name == "h264"


def test_parse_ffprobe_metadata_rejects_missing_video_stream() -> None:
    with pytest.raises(NoVideoStreamError):
        parse_ffprobe_metadata(job_id="job", video_id="video", payload={"streams": [{"codec_type": "audio"}]})


def test_frame_batching_preserves_final_short_batch(tmp_path: Path) -> None:
    frames = [
        ExtractedFrame(frame_index=index, timestamp_seconds=float(index), path=tmp_path / f"frame-{index}.jpg")
        for index in range(7)
    ]

    batches = frame_batches(frames, batch_size=5)

    assert [len(batch) for batch in batches] == [5, 2]
    assert batches[1][0].frame_index == 5


def test_frames_from_paths_sorts_and_indexes(tmp_path: Path) -> None:
    paths = [tmp_path / "frame-000002.jpg", tmp_path / "frame-000001.jpg"]

    frames = frames_from_paths(paths)

    assert [frame.path.name for frame in frames] == ["frame-000001.jpg", "frame-000002.jpg"]
    assert [frame.frame_index for frame in frames] == [0, 1]

