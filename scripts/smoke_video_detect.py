import asyncio
import json
import time
from uuid import uuid4

import httpx

from app.config.settings import Settings
from app.core.security import canonical_request, sign_canonical_request


async def main() -> None:
    settings = Settings()
    service = "off-chain-agent"
    secret = settings.secret_for_service(service)
    if secret is None:
        raise SystemExit("off-chain-agent HMAC secret is not configured")

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
    nonce = str(uuid4())
    path = "/v1/videos/detect"
    signature = sign_canonical_request(
        secret,
        canonical_request(
            method="POST",
            path=path,
            timestamp=timestamp,
            nonce=nonce,
            raw_body=raw_body,
        ),
    )
    async with httpx.AsyncClient(base_url=settings.api_base_url or "http://localhost:8080") as client:
        response = await client.post(
            path,
            content=raw_body,
            headers={
                "content-type": "application/json",
                "x-yral-service": service,
                "x-yral-timestamp": timestamp,
                "x-yral-nonce": nonce,
                "x-yral-signature": signature,
            },
        )
        print(response.status_code)
        print(response.text)


if __name__ == "__main__":
    asyncio.run(main())

