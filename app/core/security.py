import hashlib
import hmac
import string

SIGNATURE_HEX_LENGTH = 64
HEX_DIGITS = set(string.hexdigits)


def body_sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def build_signature_message(
    *,
    timestamp: str,
    method: str,
    path: str,
    body: bytes,
) -> bytes:
    return "\n".join(
        (
            timestamp,
            method.upper(),
            path,
            body_sha256(body),
        )
    ).encode("utf-8")


def signature_has_valid_shape(signature: str) -> bool:
    return (
        len(signature) == SIGNATURE_HEX_LENGTH
        and all(character in HEX_DIGITS for character in signature)
    )


def sign_request(
    secret: str,
    *,
    timestamp: str,
    method: str,
    path: str,
    body: bytes,
) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        build_signature_message(timestamp=timestamp, method=method, path=path, body=body),
        hashlib.sha256,
    ).hexdigest()


def verify_signature(
    secret: str,
    *,
    timestamp: str,
    method: str,
    path: str,
    body: bytes,
    signature: str,
) -> bool:
    if not signature_has_valid_shape(signature):
        return False
    expected = sign_request(secret, timestamp=timestamp, method=method, path=path, body=body)
    return hmac.compare_digest(expected, signature)
