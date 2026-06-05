from app.core.security import body_sha256, build_signature_message, sign_request, verify_signature


def test_signature_message_uses_expected_shape() -> None:
    body = b'{"video_id":"v1"}'
    message = build_signature_message(
        timestamp="1710000000",
        method="post",
        path="/v1/videos/detect",
        body=body,
    )

    assert message == f"1710000000\nPOST\n/v1/videos/detect\n{body_sha256(body)}".encode()


def test_signature_message_uses_empty_body_hash_for_get() -> None:
    message = build_signature_message(
        timestamp="1710000000",
        method="GET",
        path="/v1/videos/video-1/status",
        body=b"",
    )

    assert message == f"1710000000\nGET\n/v1/videos/video-1/status\n{body_sha256(b'')}".encode()


def test_signature_round_trip() -> None:
    signature = sign_request(
        "secret",
        timestamp="1710000000",
        method="POST",
        path="/v1/videos/detect",
        body=b"{}",
    )

    assert verify_signature(
        "secret",
        timestamp="1710000000",
        method="POST",
        path="/v1/videos/detect",
        body=b"{}",
        signature=signature,
    )
    assert not verify_signature(
        "secret",
        timestamp="1710000000",
        method="POST",
        path="/v1/videos/detect",
        body=b"{}",
        signature="bad",
    )


def test_malformed_signature_is_rejected_without_compare_error() -> None:
    assert not verify_signature(
        "secret",
        timestamp="1710000000",
        method="POST",
        path="/v1/videos/detect",
        body=b"{}",
        signature="not-hex",
    )
