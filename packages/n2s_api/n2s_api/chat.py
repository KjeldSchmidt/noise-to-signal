"""Contracts for news chat (web ↔ news_chat worker)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ChatScope = Literal["brief", "thread"]
ChatRole = Literal["user", "assistant"]
RefusalReason = Literal["ok", "off_topic", "injection"]

MAX_MESSAGE_CHARS = 2000
MAX_HISTORY_TURNS = 12
MAX_CHUNKS = 20
MAX_CHUNK_CHARS = 2500


class ContextChunk(BaseModel):
    """One grounded article/passage for the answer model (untrusted DATA)."""

    model_config = ConfigDict(frozen=True)

    article_id: int | None = None
    title: str = ""
    source: str = ""
    published_at: str = ""
    summary: str = ""
    story_label: str = ""
    impact_tier: str = ""
    place_label: str = ""
    url: str = ""

    @field_validator("title", "source", "story_label", "impact_tier", "place_label", "url")
    @classmethod
    def _strip_short(cls, value: str) -> str:
        return (value or "").strip()[:300]

    @field_validator("summary")
    @classmethod
    def _truncate_summary(cls, value: str) -> str:
        return (value or "").strip()[:MAX_CHUNK_CHARS]

    @field_validator("published_at")
    @classmethod
    def _published(cls, value: str) -> str:
        return (value or "").strip()[:64]


class ChatHistoryMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: ChatRole
    content: str

    @field_validator("content")
    @classmethod
    def _content(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("content must be non-empty")
        return text[:MAX_MESSAGE_CHARS]


class ChatWorkerRequest(BaseModel):
    """Payload sent from web to the news_chat Lambda (sync invoke)."""

    model_config = ConfigDict(frozen=True)

    scope: ChatScope
    scope_id: int | None = None
    message: str
    history: list[ChatHistoryMessage] = Field(default_factory=list)
    chunks: list[ContextChunk] = Field(default_factory=list)

    @field_validator("message")
    @classmethod
    def _message(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("message must be non-empty")
        if len(text) > MAX_MESSAGE_CHARS:
            raise ValueError(f"message exceeds {MAX_MESSAGE_CHARS} characters")
        return text

    @field_validator("history")
    @classmethod
    def _history(cls, value: list[ChatHistoryMessage]) -> list[ChatHistoryMessage]:
        if len(value) > MAX_HISTORY_TURNS:
            raise ValueError(f"history exceeds {MAX_HISTORY_TURNS} turns")
        return value

    @field_validator("chunks")
    @classmethod
    def _chunks(cls, value: list[ContextChunk]) -> list[ContextChunk]:
        if len(value) > MAX_CHUNKS:
            raise ValueError(f"chunks exceeds {MAX_CHUNKS}")
        return value


class ChatWorkerResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    refused: bool = False
    reason: RefusalReason = "ok"
    reply: str = ""
    message: str = ""

    @field_validator("reply", "message")
    @classmethod
    def _text(cls, value: str) -> str:
        return (value or "").strip()
