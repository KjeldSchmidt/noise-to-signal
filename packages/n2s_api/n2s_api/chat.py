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
MAX_CITATIONS = 10
MAX_SEARCH_QUERY_CHARS = 500
EMBEDDING_DIMENSIONS = 1024


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


class ChatCitation(BaseModel):
    """Article link the UI may render under an assistant reply."""

    model_config = ConfigDict(frozen=True)

    article_id: int
    title: str = ""
    url: str = ""

    @field_validator("title", "url")
    @classmethod
    def _strip_short(cls, value: str) -> str:
        return (value or "").strip()[:300]


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
    user_id: int
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
    citations: list[ChatCitation] = Field(default_factory=list)

    @field_validator("reply", "message")
    @classmethod
    def _text(cls, value: str) -> str:
        return (value or "").strip()

    @field_validator("citations")
    @classmethod
    def _citations(cls, value: list[ChatCitation]) -> list[ChatCitation]:
        if len(value) > MAX_CITATIONS:
            return value[:MAX_CITATIONS]
        return value


class ArticleSearchRequest(BaseModel):
    """Internal API: title + optional embedding ANN article search."""

    model_config = ConfigDict(frozen=True)

    query: str
    user_id: int
    embedding: list[float] | None = None
    limit: int = Field(default=10, ge=1, le=MAX_CHUNKS)
    exclude_article_ids: list[int] = Field(default_factory=list)

    @field_validator("query")
    @classmethod
    def _query(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("query must be non-empty")
        return text[:MAX_SEARCH_QUERY_CHARS]

    @field_validator("embedding")
    @classmethod
    def _embedding_dims(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return None
        if len(value) != EMBEDDING_DIMENSIONS:
            raise ValueError(f"embedding must have exactly {EMBEDDING_DIMENSIONS} dimensions")
        return value


class ArticleSearchResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    results: list[ContextChunk] = Field(default_factory=list)
