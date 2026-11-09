"""Cohere Embed Multilingual v3 via Amazon Bedrock."""

from __future__ import annotations

import json
import os
from typing import Any

import boto3

EMBEDDING_MODEL_ID = "cohere.embed-multilingual-v3"
# Cohere Embed v3: ~512 tokens / ~2048 characters per text.
_MAX_CHARS = 2000


def embed_text(text: str, *, input_type: str = "clustering") -> list[float]:
    """Return a 1024-d embedding for a single text. Raises on API/shape errors."""
    vectors = embed_texts([text], input_type=input_type)
    return vectors[0]


def embed_texts(
    texts: list[str],
    *,
    input_type: str = "clustering",
) -> list[list[float]]:
    if not texts:
        return []

    truncated = [(t or "")[:_MAX_CHARS] for t in texts]
    region = (
        os.environ.get("BEDROCK_REGION")
        or os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "eu-central-1"
    )
    client = boto3.client("bedrock-runtime", region_name=region)
    body = {
        "texts": truncated,
        "input_type": input_type,
        "truncate": "END",
    }
    response = client.invoke_model(
        modelId=EMBEDDING_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(body),
    )
    payload: dict[str, Any] = json.loads(response["body"].read())
    embeddings = payload.get("embeddings")
    if not isinstance(embeddings, list) or len(embeddings) != len(truncated):
        raise RuntimeError("unexpected Bedrock embed response shape")
    out: list[list[float]] = []
    for row in embeddings:
        if not isinstance(row, list) or len(row) != 1024:
            raise RuntimeError("embedding must be 1024 floats")
        out.append([float(x) for x in row])
    return out


def build_embed_input(*, title: str, summary: str) -> str:
    title = (title or "").strip()
    summary = (summary or "").strip()
    if title and summary:
        return f"{title}\n\n{summary}"
    return title or summary
