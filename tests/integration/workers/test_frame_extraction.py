import shutil
from pathlib import Path

import pytest

from app.services.frame_extraction_service import FrameExtractionService
from app.utils.subprocess import run_subprocess


@pytest.mark.asyncio
async def test_probe_extract_and_batch_tiny_video(test_settings, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("ffmpeg/ffprobe not installed")

    source_path = tmp_path / "source.mp4"
    frames_dir = tmp_path / "frames"
    await run_subprocess(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=64x64:rate=1:duration=2",
            "-pix_fmt",
            "yuv420p",
            str(source_path),
        ],
        timeout_seconds=30,
    )

    service = FrameExtractionService(test_settings)
    metadata = await service.probe(job_id="job", video_id="video", source_path=source_path)
    frames = await service.extract_frames(source_path, frames_dir)

    assert metadata.has_video_stream is True
    assert metadata.width == 64
    assert 1 <= len(frames) <= 3
    assert frames[0].path.exists()

