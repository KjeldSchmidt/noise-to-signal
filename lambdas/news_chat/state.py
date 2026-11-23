"""LangGraph state for news_chat."""

from __future__ import annotations

from typing import Annotated, NotRequired, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from n2s_api import ChatCitation, ChatHistoryMessage, ContextChunk


class ChatState(TypedDict):
    """Full chat turn: request inputs, agent messages, and response fields."""

    # From ChatWorkerRequest (set at invoke)
    scope: str
    scope_id: int | None
    user_id: int
    message: str
    history: list[ChatHistoryMessage]
    chunks: list[ContextChunk]

    # Classifier
    allowed: NotRequired[bool]
    refusal_reason: NotRequired[str]
    refusal_message: NotRequired[str]

    # Answer agent
    messages: Annotated[list[BaseMessage], add_messages]
    tool_rounds: NotRequired[int]
    known_by_id: NotRequired[dict[int, ContextChunk]]
    searched_ids: NotRequired[list[int]]

    # Final response fields (mapped to ChatWorkerResponse)
    refused: NotRequired[bool]
    reply: NotRequired[str]
    citations: NotRequired[list[ChatCitation]]
