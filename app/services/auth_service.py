import time

from starlette.datastructures import Headers

from app.config.settings import Settings
from app.core.security import canonical_request, verify_signature
from app.errors import codes
from app.errors.base import AppError
from app.middleware.signed_request import (
    NONCE_HEADER,
    SERVICE_HEADER,
    SIGNATURE_HEADER,
    SIGNED_REQUEST_HEADERS,
    TIMESTAMP_HEADER,
)
from app.repositories.kvrocks.auth_nonce_repository import AuthNonceRepository
from app.schemas.auth import SignedRequestContext


class AuthService:
    def __init__(self, settings: Settings, nonce_repository: AuthNonceRepository) -> None:
        self._settings = settings
        self._nonce_repository = nonce_repository

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
            raise AppError(codes.AUTH_MISSING_HEADERS, "missing HMAC authentication headers", status_code=401)

        service_name = headers[SERVICE_HEADER]
        timestamp_raw = headers[TIMESTAMP_HEADER]
        nonce = headers[NONCE_HEADER]
        signature = headers[SIGNATURE_HEADER]

        secret = self._settings.secret_for_service(service_name)
        if secret is None:
            raise AppError(codes.AUTH_UNKNOWN_SERVICE, "unknown service", status_code=401)

        try:
            timestamp = int(timestamp_raw)
        except ValueError as exc:
            raise AppError(codes.AUTH_BAD_TIMESTAMP, "timestamp must be unix seconds", status_code=401) from exc

        now = int(time.time())
        if abs(now - timestamp) > self._settings.auth_timestamp_skew_seconds:
            raise AppError(codes.AUTH_TIMESTAMP_OUT_OF_RANGE, "timestamp outside allowed skew", status_code=401)

        canonical = canonical_request(
            method=method,
            path=path,
            timestamp=timestamp_raw,
            nonce=nonce,
            raw_body=raw_body,
        )
        if not verify_signature(secret, canonical, signature):
            raise AppError(codes.AUTH_BAD_SIGNATURE, "invalid signature", status_code=401)

        stored = await self._nonce_repository.store_nonce_once(
            service_name=service_name,
            nonce=nonce,
            ttl_seconds=self._settings.auth_nonce_ttl_seconds,
        )
        if not stored:
            raise AppError(codes.AUTH_REPLAYED_NONCE, "replayed nonce", status_code=401)

        return SignedRequestContext(service_name=service_name, nonce=nonce, timestamp=timestamp)
