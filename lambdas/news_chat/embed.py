"""Cohere Embed Multilingual v3 via LangChain BedrockEmbeddings (query path)."""

from __future__ import annotations

import os

from langchain_aws import BedrockEmbeddings
from n2s_api.tunables import EMBEDDING_MODEL_ID

# Match stored Article.embedding input_type (clustering) for v1 ANN consistency.
_DEFAULT_INPUT_TYPE = "clustering"
_MAX_CHARS = 2000

_embeddings_cache: dict[str, BedrockEmbeddings] = {}


def _bedrock_region() -> str:
    return (
        os.environ.get("BEDROCK_REGION")
        or os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "eu-central-1"
    )


def get_embeddings(*, input_type: str = _DEFAULT_INPUT_TYPE) -> BedrockEmbeddings:
    cached = _embeddings_cache.get(input_type)
    if cached is not None:
        return cached
    embeddings = BedrockEmbeddings(
        model_id=EMBEDDING_MODEL_ID,
        region_name=_bedrock_region(),
        model_kwargs={"input_type": input_type, "truncate": "END"},
    )
    _embeddings_cache[input_type] = embeddings
    return embeddings


def embed_text(text: str, *, input_type: str = _DEFAULT_INPUT_TYPE) -> list[float]:
    """Return a 1024-d embedding for a single text. Raises on API/shape errors."""
    truncated = (text or "")[:_MAX_CHARS]
    vectors = get_embeddings(input_type=input_type).embed_documents([truncated])
    if not isinstance(vectors, list) or len(vectors) != 1:
        raise RuntimeError("unexpected Bedrock embed response shape")
    row = vectors[0]
    if not isinstance(row, list) or len(row) != 1024:
        raise RuntimeError("embedding must be 1024 floats")
    return [float(x) for x in row]
