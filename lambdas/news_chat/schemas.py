"""Structured LLM schemas for news_chat graph nodes."""

from __future__ import annotations

from typing import Literal

from n2s_api import ChatCitation
from pydantic import BaseModel, Field

RefusalReason = Literal["ok", "off_topic", "injection"]


class ScopeDecision(BaseModel):
    allowed: bool
    reason: RefusalReason = Field(description="ok if allowed; otherwise off_topic or injection")


class AnswerPayload(BaseModel):
    reply: str = Field(
        description=(
            "Concise answer for the user. For article lists use Markdown "
            "[Title](url) links; do not dump bare URLs or a sources footer."
        )
    )
    citations: list[ChatCitation] = Field(
        default_factory=list,
        description=(
            "Articles you relied on from DATA / search results. "
            "Only include article_id values that appeared in the provided articles."
        ),
    )
