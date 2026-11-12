"""Bedrock chat models for scope classification and grounded answers."""

from __future__ import annotations

import os

from langchain.chat_models import init_chat_model

CLASSIFIER_MODEL_ID = os.environ.get(
    "BEDROCK_CHAT_CLASSIFIER_MODEL_ID",
    "eu.amazon.nova-micro-v1:0",
)
ANSWER_MODEL_ID = os.environ.get(
    "BEDROCK_CHAT_ANSWER_MODEL_ID",
    "eu.amazon.nova-lite-v1:0",
)

_classifier = None
_answer = None


def _bedrock_region() -> str:
    return (
        os.environ.get("BEDROCK_REGION")
        or os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "eu-central-1"
    )


def get_classifier_model():
    global _classifier
    if _classifier is None:
        _classifier = init_chat_model(
            CLASSIFIER_MODEL_ID,
            model_provider="bedrock_converse",
            region_name=_bedrock_region(),
            temperature=0.0,
            max_tokens=200,
        )
    return _classifier


def get_answer_model():
    global _answer
    if _answer is None:
        _answer = init_chat_model(
            ANSWER_MODEL_ID,
            model_provider="bedrock_converse",
            region_name=_bedrock_region(),
            temperature=0.2,
            max_tokens=800,
        )
    return _answer
