"""Run the news_chat LangGraph and map state → ChatWorkerResponse."""

from __future__ import annotations

from typing import Literal, cast

from n2s_api import ChatCitation, ChatWorkerRequest, ChatWorkerResponse

from graph import chat_graph
from state import ChatState

RefusalReason = Literal["ok", "off_topic", "injection"]


def _load_brief_preferences(user_id: int) -> list[str]:
    if not user_id:
        return []
    try:
        from n2s_preferences import get_preference_client
    except ImportError:
        return []
    client = get_preference_client()
    if client is None:
        return []
    return client.retrieve_preferences(user_id, top_k=10)


def _initial_state(req: ChatWorkerRequest) -> ChatState:
    preferences: list[str] = []
    if req.scope == "brief":
        preferences = _load_brief_preferences(req.user_id)
    return {
        "scope": req.scope,
        "scope_id": req.scope_id,
        "user_id": req.user_id,
        "message": req.message,
        "history": list(req.history),
        "chunks": list(req.chunks),
        "preferences": preferences,
        "messages": [],
    }


def _to_response(final: dict[str, object]) -> ChatWorkerResponse:
    if final.get("refused"):
        raw_reason = final.get("refusal_reason")
        reason: RefusalReason = (
            cast(RefusalReason, raw_reason)
            if raw_reason in ("ok", "off_topic", "injection")
            else "off_topic"
        )
        return ChatWorkerResponse(
            refused=True,
            reason=reason,
            reply="",
            message=str(final.get("refusal_message") or ""),
            citations=[],
        )

    citations_raw = final.get("citations") or []
    citations: list[ChatCitation] = []
    if isinstance(citations_raw, list):
        for item in citations_raw:
            if isinstance(item, ChatCitation):
                citations.append(item)
            elif isinstance(item, dict):
                citations.append(ChatCitation.model_validate(item))

    return ChatWorkerResponse(
        refused=False,
        reason="ok",
        reply=str(final.get("reply") or ""),
        message="",
        citations=citations,
    )


def run_chat(req: ChatWorkerRequest) -> ChatWorkerResponse:
    """Invoke the compiled chat graph for one worker request."""
    final = chat_graph.invoke(_initial_state(req))
    return _to_response(final)
