"""Bedrock chat model for story-thread digests."""

from __future__ import annotations

import os

from langchain.chat_models import init_chat_model
from n2s_api.tunables import STORY_SUMMARY_MODEL_ID
from n2s_observability import model_tracing_kwargs

SUMMARY_MODEL_ID = STORY_SUMMARY_MODEL_ID

_summary = None


def _bedrock_region() -> str:
    return (
        os.environ.get("BEDROCK_REGION")
        or os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "eu-central-1"
    )


def get_summary_model():
    global _summary
    if _summary is None:
        _summary = init_chat_model(
            SUMMARY_MODEL_ID,
            model_provider="bedrock_converse",
            region_name=_bedrock_region(),
            temperature=0.2,
            max_tokens=700,
            **model_tracing_kwargs(),
        )
    return _summary
