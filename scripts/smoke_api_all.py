#!/usr/bin/env python3
"""Smoke-test all live API endpoints except video."""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

from app.config.settings import Settings
from app.core.security import sign_request

DEFAULT_BASE_URL = "https://nsfw.ansuman.yral.com"
DEFAULT_IMAGES_DIR = Path("test_resource/images")
DEFAULT_HQ_IMAGES_DIR = Path("test_resource/hq_images")
DEFAULT_PROMPTS_FILE = Path("test_resource/text_prompts/prompts.txt")

DEFAULT_TEXT_PROMPTS = [
    "A cinematic dance video on a beach at sunset.",
    "A person walking through a quiet city park in the morning.",
]

# Public URLs the production server can fetch (detect-url cannot use local files).
SAFE_IMAGE_URL = "https://picsum.photos/seed/nsfw-smoke/320/240"

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".avif", ".gif", ".bmp"}


@dataclass
class EndpointResult:
    name: str
    method: str
    path: str
    status_code: int
    elapsed_ms: float
    ok: bool
    body: object
    case_id: str | None = None
    error: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test all non-video API endpoints.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL (no /docs suffix).")
    parser.add_argument("--images-dir", type=Path, default=DEFAULT_IMAGES_DIR, help="Local images for base64 detect.")
    parser.add_argument(
        "--include-hq",
        action="store_true",
        help="Also run base64 cases from test_resource/hq_images.",
    )
    parser.add_argument(
        "--prompts-file",
        type=Path,
        default=DEFAULT_PROMPTS_FILE,
        help="Optional text prompts file (one prompt per non-empty line).",
    )
    parser.add_argument("--timeout", type=float, default=120.0, help="Per-request timeout seconds.")
    parser.add_argument("--quick", action="store_true", help="Only one safe image and one text prompt.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON report.")
    return parser.parse_args()


def signed_headers(*, secret: str, method: str, path: str, raw_body: bytes) -> dict[str, str]:
    timestamp = str(int(time.time()))
    return {
        "content-type": "application/json",
        "x-internal-timestamp": timestamp,
        "x-internal-signature": sign_request(
            secret,
            timestamp=timestamp,
            method=method,
            path=path,
            body=raw_body,
        ),
    }


def is_success(name: str, status_code: int) -> bool:
    if name in {"health", "ready"}:
        return status_code == 200
    return 200 <= status_code < 300


def load_text_prompts(prompts_file: Path) -> list[str]:
    if prompts_file.is_file():
        prompts = [line.strip() for line in prompts_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        if prompts:
            return prompts
    return DEFAULT_TEXT_PROMPTS


def discover_images(*dirs: Path) -> list[Path]:
    images: list[Path] = []
    for directory in dirs:
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
                images.append(path)
    return images


def pick_quick_image(images: list[Path]) -> list[Path]:
    for path in images:
        if "safe" in path.name.lower():
            return [path]
    return images[:1]


async def get_json(client: httpx.AsyncClient, path: str, timeout: float) -> EndpointResult:
    started = time.perf_counter()
    try:
        response = await client.get(path, timeout=timeout)
        elapsed_ms = (time.perf_counter() - started) * 1000
        try:
            body: object = response.json()
        except json.JSONDecodeError:
            body = response.text
        name = path.strip("/").split("/")[-1]
        return EndpointResult(
            name=name,
            method="GET",
            path=path,
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
            ok=is_success(name, response.status_code),
            body=body,
            case_id=f"preflight:{name}",
        )
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = (time.perf_counter() - started) * 1000
        name = path.strip("/").split("/")[-1]
        return EndpointResult(
            name=name,
            method="GET",
            path=path,
            status_code=0,
            elapsed_ms=elapsed_ms,
            ok=False,
            body=None,
            case_id=f"preflight:{name}",
            error=str(exc),
        )


async def post_signed(
    client: httpx.AsyncClient,
    *,
    secret: str,
    name: str,
    path: str,
    body: dict[str, object],
    timeout: float,
    case_id: str,
) -> EndpointResult:
    raw_body = json.dumps(body, separators=(",", ":")).encode("utf-8")
    started = time.perf_counter()
    try:
        response = await client.post(
            path,
            content=raw_body,
            headers=signed_headers(secret=secret, method="POST", path=path, raw_body=raw_body),
            timeout=timeout,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        try:
            payload: object = response.json()
        except json.JSONDecodeError:
            payload = response.text
        return EndpointResult(
            name=name,
            method="POST",
            path=path,
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
            ok=is_success(name, response.status_code),
            body=payload,
            case_id=case_id,
        )
    except Exception as exc:  # noqa: BLE001
        elapsed_ms = (time.perf_counter() - started) * 1000
        return EndpointResult(
            name=name,
            method="POST",
            path=path,
            status_code=0,
            elapsed_ms=elapsed_ms,
            ok=False,
            body=None,
            case_id=case_id,
            error=str(exc),
        )


def print_report(base_url: str, results: list[EndpointResult]) -> None:
    passed = sum(1 for item in results if item.ok)
    print(f"Base URL: {base_url}")
    print(f"Summary: {passed}/{len(results)} cases OK\n")
    for item in results:
        status = "PASS" if item.ok else "FAIL"
        label = f" :: {item.case_id}" if item.case_id else ""
        print(f"[{status}] {item.method} {item.path}{label} -> {item.status_code} ({item.elapsed_ms:.0f} ms)")
        if item.error:
            print(f"       error: {item.error}")
        elif not item.ok:
            if isinstance(item.body, dict):
                print(f"       body: {json.dumps(item.body, indent=2)}")
            elif isinstance(item.body, str) and len(item.body) > 400:
                print(f"       body: {item.body[:400]}...")
            else:
                print(f"       body: {item.body}")


async def run(args: argparse.Namespace) -> int:
    settings = Settings()
    secret = settings.internal_request_secret()
    if secret is None:
        print("INTERNAL_REQUEST_HMAC_SECRET is not configured in .env", file=sys.stderr)
        return 2

    base_url = args.base_url.rstrip("/")
    image_dirs = [args.images_dir]
    if args.include_hq:
        image_dirs.append(DEFAULT_HQ_IMAGES_DIR)

    images = discover_images(*image_dirs)
    if not images:
        print(f"No images found under: {', '.join(str(path) for path in image_dirs)}", file=sys.stderr)
        return 2
    if args.quick:
        images = pick_quick_image(images)

    text_prompts = load_text_prompts(args.prompts_file)
    if args.quick:
        text_prompts = text_prompts[:1]

    results: list[EndpointResult] = []
    async with httpx.AsyncClient(base_url=base_url) as client:
        results.append(await get_json(client, "/health", args.timeout))
        results.append(await get_json(client, "/ready", args.timeout))

        for index, prompt in enumerate(text_prompts, start=1):
            results.append(
                await post_signed(
                    client,
                    secret=secret,
                    name="text_detect",
                    path="/v1/text/detect",
                    body={"text": prompt},
                    timeout=args.timeout,
                    case_id=f"text:{index}",
                )
            )

        results.append(
            await post_signed(
                client,
                secret=secret,
                name="image_detect_url",
                path="/v1/images/detect-url",
                body={"image_url": SAFE_IMAGE_URL},
                timeout=args.timeout,
                case_id="url:public_safe",
            )
        )

        for image_path in images:
            image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
            results.append(
                await post_signed(
                    client,
                    secret=secret,
                    name="image_detect_base64",
                    path="/v1/images/detect-base64",
                    body={"image_base64": image_b64},
                    timeout=args.timeout,
                    case_id=f"base64:{image_path.name}",
                )
            )

    if args.json:
        print(json.dumps({"base_url": base_url, "results": [asdict(item) for item in results]}, indent=2))
    else:
        print_report(base_url, results)

    return 0 if all(item.ok for item in results) else 1


def main() -> None:
    raise SystemExit(asyncio.run(run(parse_args())))


if __name__ == "__main__":
    main()
