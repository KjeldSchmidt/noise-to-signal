"""Shared Bedrock chat model for structured extract calls."""

from __future__ import annotations

import os

from langchain.chat_models import init_chat_model

EXTRACT_MODEL_ID = os.environ.get("BEDROCK_EXTRACT_MODEL_ID", "amazon.nova-micro-v1:0")

_model = None


def _bedrock_region() -> str:
    return (
        os.environ.get("BEDROCK_REGION")
        or os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "eu-central-1"
    )


def get_extract_model():
    global _model
    if _model is None:
        _model = init_chat_model(
            EXTRACT_MODEL_ID,
            model_provider="bedrock_converse",
            region_name=_bedrock_region(),
            temperature=0.0,
            max_tokens=400,
        )
    return _model
