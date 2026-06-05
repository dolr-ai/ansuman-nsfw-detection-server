import asyncio
import json
import time
from uuid import uuid4

import httpx

from app.config.settings import Settings
from app.core.security import sign_request


async def main() -> None:
    settings = Settings()
    secret = settings.internal_request_secret()
    if secret is None:
        raise SystemExit("internal request HMAC secret is not configured")

    body = {
        "job_id": "nsfw:smoke-video:nsfw_policy_v1:",
        "video_id": "smoke-video",
        "publisher_user_id": "smoke-user",
        "source_video_uri": "https://example.com/smoke.mp4",
        "policy_version": "nsfw_policy_v1",
        "trace_id": str(uuid4()),
    }
    raw_body = json.dumps(body, separators=(",", ":")).encode("utf-8")
    timestamp = str(int(time.time()))
    path = "/v1/videos/detect"
    signature = sign_request(
        secret,
        timestamp=timestamp,
        method="POST",
        path=path,
        body=raw_body,
    )
    async with httpx.AsyncClient(base_url=settings.api_base_url or "http://localhost:8080") as client:
        response = await client.post(
            path,
            content=raw_body,
            headers={
                "content-type": "application/json",
                "x-internal-timestamp": timestamp,
                "x-internal-signature": signature,
            },
        )
        print(response.status_code)
        print(response.text)


if __name__ == "__main__":
    asyncio.run(main())
