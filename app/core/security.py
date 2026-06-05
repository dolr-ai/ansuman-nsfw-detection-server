import hashlib
import hmac


def body_sha256(raw_body: bytes) -> str:
    return hashlib.sha256(raw_body).hexdigest()


def canonical_request(
    *,
    method: str,
    path: str,
    timestamp: str,
    nonce: str,
    raw_body: bytes,
) -> str:
    return "\n".join(
        (
            method.upper(),
            path,
            timestamp,
            nonce,
            body_sha256(raw_body),
        )
    )


def sign_canonical_request(secret: str, canonical: str) -> str:
    return hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_signature(secret: str, canonical: str, signature: str) -> bool:
    expected = sign_canonical_request(secret, canonical)
    return hmac.compare_digest(expected, signature)

