"""Contracts for bulk article embedding export (theme analysis)."""

from __future__ import annotations

import base64
import struct

from pydantic import BaseModel, ConfigDict, Field, field_validator

from n2s_api.chat import EMBEDDING_DIMENSIONS

_FLOAT32_BYTES = 4
_EXPECTED_RAW_LEN = EMBEDDING_DIMENSIONS * _FLOAT32_BYTES


def encode_embedding_f32_b64(values: list[float]) -> str:
    """Little-endian float32 vectors as ASCII base64."""
    if len(values) != EMBEDDING_DIMENSIONS:
        raise ValueError(f"embedding must have exactly {EMBEDDING_DIMENSIONS} dimensions")
    raw = struct.pack(f"<{EMBEDDING_DIMENSIONS}f", *[float(x) for x in values])
    return base64.b64encode(raw).decode("ascii")


def decode_embedding_f32_b64(payload: str) -> list[float]:
    """Decode little-endian float32 base64 back to 1024 floats."""
    raw = base64.b64decode(payload.encode("ascii"), validate=True)
    if len(raw) != _EXPECTED_RAW_LEN:
        raise ValueError(f"embedding_b64 must decode to {_EXPECTED_RAW_LEN} bytes, got {len(raw)}")
    return list(struct.unpack(f"<{EMBEDDING_DIMENSIONS}f", raw))


class ArticleEmbeddingExportRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    title: str
    theme_slugs: list[str] = Field(default_factory=list)
    embedding_b64: str

    @field_validator("embedding_b64")
    @classmethod
    def _embedding_b64_shape(cls, value: str) -> str:
        # Validate round-trip length without keeping the float list.
        decode_embedding_f32_b64(value)
        return value


class ArticleEmbeddingExportResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    articles: list[ArticleEmbeddingExportRow] = Field(default_factory=list)
    next_cursor: int | None = None
