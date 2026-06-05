from app.core.security import body_sha256, canonical_request, sign_canonical_request, verify_signature


def test_canonical_request_uses_expected_shape() -> None:
    canonical = canonical_request(
        method="post",
        path="/v1/videos/detect",
        timestamp="1710000000",
        nonce="nonce-1",
        raw_body=b'{"video_id":"v1"}',
    )

    assert canonical == "\n".join(
        [
            "POST",
            "/v1/videos/detect",
            "1710000000",
            "nonce-1",
            body_sha256(b'{"video_id":"v1"}'),
        ]
    )


def test_signature_round_trip() -> None:
    canonical = "POST\n/v1/videos/detect\n1710000000\nnonce\nhash"
    signature = sign_canonical_request("secret", canonical)

    assert verify_signature("secret", canonical, signature)
    assert not verify_signature("secret", canonical, "bad")

