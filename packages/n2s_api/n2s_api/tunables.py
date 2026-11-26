"""Product/ops tunables: code defaults, overridable via env at import time.

Edit defaults here. Override with ``N2S_*`` (product knobs) or ``BEDROCK_*``
(model IDs). Infra-only values (EventBridge schedules) stay in Terraform —
see the knobs registry in the repo root README.
"""

from __future__ import annotations

import os
from datetime import timedelta


def _env_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip()


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw.strip())


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw.strip())


# --- Brief ---
BRIEF_TTL_HOURS = _env_float("N2S_BRIEF_TTL_HOURS", 6.0)
BRIEF_TTL = timedelta(hours=BRIEF_TTL_HOURS)
INTERIM_LIMIT = _env_int("N2S_INTERIM_LIMIT", 12)
CANDIDATE_LIMIT = _env_int("N2S_CANDIDATE_LIMIT", 30)
MAX_BRIEF_ITEMS = _env_int("N2S_MAX_BRIEF_ITEMS", 8)

THREAD_SUMMARY_TTL_HOURS = _env_float("N2S_THREAD_SUMMARY_TTL_HOURS", 6.0)
THREAD_SUMMARY_TTL = timedelta(hours=THREAD_SUMMARY_TTL_HOURS)

# --- Chat rate limits ---
CHAT_MINUTE_LIMIT = _env_int("N2S_CHAT_MINUTE_LIMIT", 10)
CHAT_DAY_LIMIT = _env_int("N2S_CHAT_DAY_LIMIT", 100)

# --- Chat payload caps ---
MAX_MESSAGE_CHARS = _env_int("N2S_MAX_MESSAGE_CHARS", 2000)
MAX_HISTORY_TURNS = _env_int("N2S_MAX_HISTORY_TURNS", 12)
MAX_CHUNKS = _env_int("N2S_MAX_CHUNKS", 20)
MAX_CHUNK_CHARS = _env_int("N2S_MAX_CHUNK_CHARS", 2500)
MAX_CITATIONS = _env_int("N2S_MAX_CITATIONS", 10)
MAX_SEARCH_QUERY_CHARS = _env_int("N2S_MAX_SEARCH_QUERY_CHARS", 500)

# --- Chat cost ---
MAX_TOOL_ROUNDS = _env_int("N2S_MAX_TOOL_ROUNDS", 2)

# --- Model IDs (deploy overrides via existing BEDROCK_* env names) ---
BRIEF_MODEL_ID = _env_str("BEDROCK_BRIEF_MODEL_ID", "eu.amazon.nova-lite-v1:0")
CHAT_CLASSIFIER_MODEL_ID = _env_str(
    "BEDROCK_CHAT_CLASSIFIER_MODEL_ID",
    "eu.amazon.nova-micro-v1:0",
)
CHAT_ANSWER_MODEL_ID = _env_str("BEDROCK_CHAT_ANSWER_MODEL_ID", "eu.amazon.nova-lite-v1:0")
EXTRACT_MODEL_ID = _env_str("BEDROCK_EXTRACT_MODEL_ID", "eu.amazon.nova-micro-v1:0")
STORY_SUMMARY_MODEL_ID = _env_str(
    "BEDROCK_STORY_SUMMARY_MODEL_ID",
    "eu.amazon.nova-lite-v1:0",
)
EMBEDDING_MODEL_ID = _env_str(
    "BEDROCK_EMBEDDING_MODEL_ID",
    "cohere.embed-multilingual-v3",
)
