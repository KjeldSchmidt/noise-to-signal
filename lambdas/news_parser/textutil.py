"""Normalize RSS title/summary text to plain strings for Article storage."""

from __future__ import annotations

import html
import re

_SCRIPT_STYLE = re.compile(r"(?is)<(script|style)\b[^>]*>.*?</\1>")
_TAGS = re.compile(r"(?s)<[^>]+>")
_WHITESPACE = re.compile(r"\s+")


def clean_text(value: str | None) -> str:
    """Unescape HTML entities, strip all tags, collapse whitespace."""
    text = value or ""
    text = html.unescape(html.unescape(text))
    text = _SCRIPT_STYLE.sub(" ", text)
    text = _TAGS.sub(" ", text)
    text = html.unescape(text)
    return _WHITESPACE.sub(" ", text).strip()
