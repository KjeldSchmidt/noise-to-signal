"""Encode/decode round-trip for float32 embedding export."""

from __future__ import annotations

from n2s_api import decode_embedding_f32_b64, encode_embedding_f32_b64


def test_encode_decode_roundtrip() -> None:
    values = [0.0] * 1024
    values[0] = 1.0
    values[511] = -0.5
    encoded = encode_embedding_f32_b64(values)
    decoded = decode_embedding_f32_b64(encoded)
    assert len(decoded) == 1024
    assert abs(decoded[0] - 1.0) < 1e-6
    assert abs(decoded[511] - (-0.5)) < 1e-6


def test_encode_rejects_bad_dims() -> None:
    try:
        encode_embedding_f32_b64([0.1, 0.2])
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
