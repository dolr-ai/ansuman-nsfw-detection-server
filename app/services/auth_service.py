import time

from starlette.datastructures import Headers

from app.config.settings import Settings
from app.core.security import verify_signature
from app.errors import codes
from app.errors.base import AppError
from app.middleware.signed_request import (
    SIGNATURE_HEADER,
    SIGNED_REQUEST_HEADERS,
    TIMESTAMP_HEADER,
)
from app.schemas.auth import SignedRequestContext


class AuthService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def authenticate(
        self,
        *,
        method: str,
        path: str,
        headers: Headers,
        raw_body: bytes,
    ) -> SignedRequestContext:
        missing = [header for header in SIGNED_REQUEST_HEADERS if not headers.get(header)]
        if missing:
            raise AppError(codes.AUTH_MISSING_HEADERS, "missing internal auth headers", status_code=401)

        secret = self._settings.internal_request_secret()
        if secret is None:
            raise AppError(codes.AUTH_BAD_SIGNATURE, "invalid internal signature", status_code=401)

        timestamp_raw = headers[TIMESTAMP_HEADER]
        signature = headers[SIGNATURE_HEADER]

        try:
            timestamp = int(timestamp_raw)
        except ValueError as exc:
            raise AppError(codes.AUTH_BAD_TIMESTAMP, "timestamp must be unix seconds", status_code=401) from exc

        now = int(time.time())
        if abs(now - timestamp) > self._settings.internal_request_max_skew_sec:
            raise AppError(codes.AUTH_TIMESTAMP_OUT_OF_RANGE, "stale internal request timestamp", status_code=401)

        if not verify_signature(
            secret,
            timestamp=timestamp_raw,
            method=method,
            path=path,
            body=raw_body,
            signature=signature,
        ):
            raise AppError(codes.AUTH_BAD_SIGNATURE, "invalid internal signature", status_code=401)

        return SignedRequestContext(timestamp=timestamp)
