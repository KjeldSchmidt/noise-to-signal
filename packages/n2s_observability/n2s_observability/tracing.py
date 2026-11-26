"""Langfuse CallbackHandler wiring + flush for serverless workers."""

from __future__ import annotations

import os
from typing import Any


def tracing_enabled() -> bool:
    """True when Langfuse public + secret keys are present."""
    return bool(
        (os.environ.get("LANGFUSE_PUBLIC_KEY") or "").strip()
        and (os.environ.get("LANGFUSE_SECRET_KEY") or "").strip()
    )


def _langfuse_tags() -> list[str]:
    tags_raw = (os.environ.get("LANGFUSE_TAGS") or "").strip()
    if not tags_raw:
        return []
    return [t.strip() for t in tags_raw.split(",") if t.strip()]


def model_tracing_kwargs() -> dict[str, Any]:
    """
    Kwargs for ``init_chat_model`` / ``BaseChatModel``.

    Prefer this over ``runnable.with_config(...)``: wrapping yields a
    ``RunnableBinding`` without ``with_structured_output`` / ``bind_tools``.
    Optional ``LANGFUSE_TAGS`` (comma-separated) becomes ``metadata.langfuse_tags``.
    """
    if not tracing_enabled():
        return {}

    from langfuse.langchain import CallbackHandler

    os.environ.setdefault("LANGCHAIN_CALLBACKS_BACKGROUND", "false")
    kwargs: dict[str, Any] = {"callbacks": [CallbackHandler()]}
    tags = _langfuse_tags()
    if tags:
        kwargs["metadata"] = {"langfuse_tags": tags}
    return kwargs


def flush_tracing() -> None:
    """Flush pending Langfuse events (call in Lambda ``finally``)."""
    if not tracing_enabled():
        return
    from langfuse import get_client

    get_client().flush()
