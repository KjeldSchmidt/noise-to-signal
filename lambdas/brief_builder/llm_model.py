"""Bedrock chat model for brief selection."""

from __future__ import annotations

import os

from langchain.chat_models import init_chat_model
from n2s_observability import model_tracing_kwargs

BRIEF_MODEL_ID = os.environ.get(
    "BEDROCK_BRIEF_MODEL_ID",
    "eu.amazon.nova-lite-v1:0",
)

_brief = None


def _bedrock_region() -> str:
    return (
        os.environ.get("BEDROCK_REGION")
        or os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "eu-central-1"
    )


def get_brief_model():
    global _brief
    if _brief is None:
        _brief = init_chat_model(
            BRIEF_MODEL_ID,
            model_provider="bedrock_converse",
            region_name=_bedrock_region(),
            temperature=0.2,
            max_tokens=2000,
            **model_tracing_kwargs(),
        )
    return _brief
