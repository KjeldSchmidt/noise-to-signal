"""Cohere Embed Multilingual v3 via LangChain BedrockEmbeddings."""

from __future__ import annotations

import os

from langchain_aws import BedrockEmbeddings

EMBEDDING_MODEL_ID = "cohere.embed-multilingual-v3"
# Cohere Embed v3: ~512 tokens / ~2048 characters per text.
_MAX_CHARS = 2000

_embeddings_cache: dict[str, BedrockEmbeddings] = {}


def _bedrock_region() -> str:
    return (
        os.environ.get("BEDROCK_REGION")
        or os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "eu-central-1"
    )


def get_embeddings(*, input_type: str = "clustering") -> BedrockEmbeddings:
    """Cached BedrockEmbeddings; model_kwargs override Cohere input_type."""
    cached = _embeddings_cache.get(input_type)
    if cached is not None:
        return cached
    embeddings = BedrockEmbeddings(
        model_id=EMBEDDING_MODEL_ID,
        region_name=_bedrock_region(),
        # Overrides LangChain's default search_document / search_query.
        model_kwargs={"input_type": input_type, "truncate": "END"},
    )
    _embeddings_cache[input_type] = embeddings
    return embeddings


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
    embeddings = get_embeddings(input_type=input_type).embed_documents(truncated)
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
