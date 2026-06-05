import argparse
import asyncio
import json
import re
import shutil
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import httpx
from httpx import ASGITransport
from pydantic import SecretStr

from app.config.settings import Settings
from app.core.lifecycle import build_gpu_moderation_service
from app.core.security import canonical_request, sign_canonical_request
from app.main import create_app
from app.repositories.kvrocks.auth_nonce_repository import InMemoryAuthNonceRepository
from app.repositories.kvrocks.queue_repository import InMemoryVideoQueueRepository
from app.services.aggregation_service import AggregationService
from app.services.frame_extraction_service import FrameExtractionService, download_video, frame_batches
from app.utils.file_cleanup import cleanup_dir
from app.utils.redaction import redact_url


URL_PATTERN = re.compile(r"https://link\.storjshare\.io/[^\])\s]+?\.mp4")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run real Storj video links through API accept + isolated pipeline.")
    parser.add_argument("--links-file", default="storj.txt")
    parser.add_argument("--limit", type=int, default=0, help="Max unique URLs to process; 0 means all.")
    parser.add_argument("--skip-gpu", action="store_true", help="Stop after download/probe/extract/batching.")
    parser.add_argument("--max-batches", type=int, default=0, help="Max GPU batches per video; 0 means all.")
    parser.add_argument("--keep-artifacts", action="store_true", help="Keep downloaded videos and frames.")
    parser.add_argument("--require-video-tools", action="store_true", default=True)
    return parser.parse_args()


def parse_storj_urls(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    urls: list[str] = []
    for match in URL_PATTERN.finditer(text):
        url = match.group(0)
        if url not in urls:
            urls.append(url)
    return urls


def signed_headers(*, secret: str, method: str, path: str, raw_body: bytes) -> dict[str, str]:
    timestamp = str(int(time.time()))
    nonce = str(uuid4())
    canonical = canonical_request(
        method=method,
        path=path,
        timestamp=timestamp,
        nonce=nonce,
        raw_body=raw_body,
    )
    return {
        "content-type": "application/json",
        "x-yral-service": "off-chain-agent",
        "x-yral-timestamp": timestamp,
        "x-yral-nonce": nonce,
        "x-yral-signature": sign_canonical_request(secret, canonical),
    }


async def accept_job(client: httpx.AsyncClient, secret: str, body: dict[str, object]) -> dict[str, object]:
    raw_body = json.dumps(body, separators=(",", ":")).encode("utf-8")
    response = await client.post(
        "/v1/videos/detect",
        content=raw_body,
        headers=signed_headers(secret=secret, method="POST", path="/v1/videos/detect", raw_body=raw_body),
    )
    response.raise_for_status()
    return response.json()


async def run_one(
    *,
    index: int,
    url: str,
    settings: Settings,
    api_client: httpx.AsyncClient,
    secret: str,
    skip_gpu: bool,
    max_batches: int,
) -> dict[str, object]:
    trace_id = f"real-smoke-{uuid4()}"
    video_id = f"real-smoke-video-{uuid4()}"
    job_id = f"nsfw:{video_id}:{settings.default_policy_version}:"
    body = {
        "job_id": job_id,
        "video_id": video_id,
        "publisher_user_id": "real-smoke-user",
        "source_video_uri": url,
        "source_object_version": "",
        "policy_version": settings.default_policy_version,
        "trace_id": trace_id,
    }
    accepted = await accept_job(api_client, secret, body)

    extraction_service = FrameExtractionService(settings)
    job_dir = await extraction_service.prepare_job_dir(job_id)
    source_path = job_dir / "source.mp4"
    summary: dict[str, object] = {
        "index": index,
        "job_id": job_id,
        "video_id": video_id,
        "url": redact_url(url),
        "api_status": accepted["status"],
        "stage": "accepted",
    }

    async with httpx.AsyncClient(follow_redirects=True) as download_client:
        await download_video(url, source_path, settings, download_client)
    summary["download_bytes"] = source_path.stat().st_size
    summary["stage"] = "downloaded"

    metadata = await extraction_service.probe(job_id=job_id, video_id=video_id, source_path=source_path)
    summary.update(
        {
            "duration_seconds": metadata.duration_seconds,
            "width": metadata.width,
            "height": metadata.height,
            "fps": metadata.fps,
            "codec_name": metadata.codec_name,
        }
    )
    summary["stage"] = "probed"

    frames = await extraction_service.extract_frames(source_path, job_dir / "frames")
    metadata = replace(metadata, frames_extracted=len(frames))
    batches = frame_batches(frames, settings.frame_batch_size)
    summary.update({"frames_extracted": len(frames), "batch_sizes": [len(batch) for batch in batches]})
    summary["stage"] = "extracted"

    if skip_gpu:
        summary["gpu_skipped"] = True
        return summary

    gpu_service = build_gpu_moderation_service(settings)
    if gpu_service is None:
        summary["gpu_skipped"] = True
        summary["gpu_skip_reason"] = "GPU settings are not configured"
        return summary

    selected_batches = batches[:max_batches] if max_batches else batches
    frame_results = []
    for batch in selected_batches:
        frame_results.extend(await gpu_service.moderate_frame_batch(batch))

    final_result = AggregationService(settings).aggregate(
        job_id=job_id,
        video_id=video_id,
        policy_version=settings.default_policy_version,
        frames=frame_results,
    )
    summary.update(
        {
            "gpu_frames_processed": len(frame_results),
            "final_is_nsfw": final_result.final_is_nsfw,
            "final_score": final_result.final_score,
            "final_top_category": final_result.final_top_category,
            "move_required": final_result.move_required,
        }
    )
    summary["stage"] = "classified"
    return summary


async def main() -> None:
    args = parse_args()
    urls = parse_storj_urls(Path(args.links_file))
    if args.limit:
        urls = urls[: args.limit]
    if not urls:
        raise SystemExit(f"no Storj URLs found in {args.links_file}")

    missing_tools = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if args.require_video_tools and missing_tools:
        raise SystemExit(f"missing required video tools: {', '.join(missing_tools)}")

    secret = "real-smoke-secret"
    temp_root = Path(tempfile.mkdtemp(prefix="nsfw-real-smoke-"))
    settings = Settings(
        service_hmac_secrets={"off-chain-agent": SecretStr(secret)},
        video_temp_root=str(temp_root),
    )
    queue = InMemoryVideoQueueRepository()
    app = create_app(
        settings=settings,
        nonce_repository=InMemoryAuthNonceRepository(),
        queue_repository=queue,
    )

    summaries: list[dict[str, object]] = []
    try:
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://real-smoke") as api_client:
            for index, url in enumerate(urls, start=1):
                try:
                    summaries.append(
                        await run_one(
                            index=index,
                            url=url,
                            settings=settings,
                            api_client=api_client,
                            secret=secret,
                            skip_gpu=args.skip_gpu,
                            max_batches=args.max_batches,
                        )
                    )
                except Exception as exc:
                    summaries.append(
                        {
                            "index": index,
                            "url": redact_url(url),
                            "stage": "failed",
                            "error_type": exc.__class__.__name__,
                            "error": str(exc),
                        }
                    )
        print(json.dumps({"temp_root": str(temp_root), "results": summaries}, indent=2, default=str))
    finally:
        if args.keep_artifacts:
            print(f"kept artifacts at {temp_root}")
        else:
            cleanup_dir(temp_root)


if __name__ == "__main__":
    asyncio.run(main())

