"""LangGraph news chat: classify → (refuse | agent ↔ tools → finalize)."""

from __future__ import annotations

import logging
from typing import Any, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from n2s_api import MAX_TOOL_ROUNDS, ChatCitation

from llm_model import get_answer_model, get_classifier_model
from prompts import (
    ANSWER_SYSTEM,
    CLASSIFIER_SYSTEM,
    REFUSAL_COPY,
    assemble_data_block,
    format_preferences,
    history_as_text,
    scope_hint_from_parts,
)
from schemas import AnswerPayload, RefusalReason, ScopeDecision
from state import ChatState
from tools import CHAT_TOOLS, collect_known_articles, filter_citations, search_articles

logger = logging.getLogger(__name__)


def _tool_call_audit(tool_calls: list[Any]) -> list[dict[str, Any]]:
    """Compact tool-call summary for logs (no preference text bodies)."""
    out: list[dict[str, Any]] = []
    for call in tool_calls:
        if isinstance(call, dict):
            name = str(call.get("name") or "")
            raw_args = call.get("args")
        else:
            name = str(getattr(call, "name", "") or "")
            raw_args = getattr(call, "args", None)
        args: dict[str, Any] = dict(raw_args) if isinstance(raw_args, dict) else {}
        if name == "save_preference":
            text = str(args.get("text") or "")
            args = {"text_chars": len(text.strip())}
        elif name == "search_articles":
            query = str(args.get("query") or "")
            if len(query) > 120:
                query = f"{query[:120]}…"
            args = {
                "query": query,
                "country_code": args.get("country_code"),
                "published_after": args.get("published_after"),
            }
        else:
            args = {}
        out.append({"name": name, "args": args})
    return out


FINAL_ANSWER_PROMPT = (
    "Provide your final answer now. Use the search_articles results and "
    "page DATA as evidence. Respect similarity scores: only list on-topic "
    "articles (prefer similarity ≳ 0.75 or clear title match); omit weak or "
    "off-topic hits. Prefer higher impact_tier among on-topic hits when the "
    "user asks for the most important stories. If listing articles, format "
    "each as `1. [Title](url)` (no bare URL lines, no ‘visit the sources’ "
    "note). For longer prose, weave titles into the narrative. Populate "
    "citations with article_id/title/url from DATA — only real article_id "
    "values. If nothing on-topic, say no matching articles were found in the "
    "user’s feeds (and time window if filtered) — never claim you lack access "
    "to a country’s or language’s news."
)

_tool_node = ToolNode(CHAT_TOOLS)


def _baseline_user_message(state: ChatState) -> str:
    data = assemble_data_block(list(state.get("chunks") or []))
    prefs = format_preferences(list(state.get("preferences") or []))
    prefs_block = f"{prefs}\n\n" if prefs else ""
    return (
        f"{scope_hint_from_parts(state['scope'], state.get('scope_id'))}\n\n"
        f"{prefs_block}"
        f"{data}\n\n"
        f"Conversation so far:\n{history_as_text(list(state.get('history') or []))}\n\n"
        f"User question:\n{state['message']}"
    )


def classify(state: ChatState) -> dict[str, Any]:
    structured = get_classifier_model().with_structured_output(ScopeDecision)
    user = (
        f"{scope_hint_from_parts(state['scope'], state.get('scope_id'))}\n"
        f"history:\n{history_as_text(list(state.get('history') or []))}\n\n"
        f"user_message:\n{state['message']}"
    )
    result = structured.invoke(
        [
            SystemMessage(content=CLASSIFIER_SYSTEM),
            HumanMessage(content=user),
        ]
    )
    decision = result if isinstance(result, ScopeDecision) else ScopeDecision.model_validate(result)
    if not decision.allowed:
        reason: RefusalReason = (
            decision.reason if decision.reason in ("off_topic", "injection") else "off_topic"
        )
        return {
            "allowed": False,
            "refusal_reason": reason,
            "refusal_message": REFUSAL_COPY.get(reason) or REFUSAL_COPY["off_topic"],
            "refused": True,
            "reply": "",
            "citations": [],
        }

    known = collect_known_articles(list(state.get("chunks") or []))
    return {
        "allowed": True,
        "refusal_reason": "ok",
        "refused": False,
        "known_by_id": known,
        "searched_ids": [],
        "tool_rounds": 0,
        "messages": [
            SystemMessage(content=ANSWER_SYSTEM),
            HumanMessage(content=_baseline_user_message(state)),
        ],
    }


def route_after_classify(state: ChatState) -> Literal["refuse", "agent"]:
    if state.get("allowed"):
        return "agent"
    return "refuse"


def refuse(state: ChatState) -> dict[str, Any]:
    """Terminal refusal — classifier already populated response fields."""
    _ = state
    return {}


def _tools_for_scope(state: ChatState) -> list[object]:
    if state.get("scope") == "brief":
        return list(CHAT_TOOLS)
    return [search_articles]


def agent(state: ChatState) -> dict[str, Any]:
    model = get_answer_model().bind_tools(_tools_for_scope(state))
    response = model.invoke(state["messages"])
    tool_calls = getattr(response, "tool_calls", None) or []
    rounds = int(state.get("tool_rounds") or 0)
    if tool_calls:
        logger.info(
            "news_chat agent tool_calls user_id=%s round=%s calls=%s",
            state.get("user_id"),
            rounds,
            _tool_call_audit(list(tool_calls)),
        )
    elif rounds == 0:
        logger.info(
            "news_chat agent answered without tools user_id=%s",
            state.get("user_id"),
        )
    return {"messages": [response]}


def route_after_agent(state: ChatState) -> Literal["tools", "finalize"]:
    last = state["messages"][-1]
    tool_calls = getattr(last, "tool_calls", None) or []
    if not tool_calls:
        return "finalize"
    if int(state.get("tool_rounds") or 0) >= MAX_TOOL_ROUNDS:
        return "finalize"
    return "tools"


def run_tools(state: ChatState) -> dict[str, Any]:
    """ToolNode executes search_articles (Command updates merge into state)."""
    result = _tool_node.invoke(state)
    updates = dict(result) if isinstance(result, dict) else {}
    updates["tool_rounds"] = int(state.get("tool_rounds") or 0) + 1
    return updates


def _reply_looks_like_empty_list_intro(reply: str) -> bool:
    text = (reply or "").strip()
    if not text:
        return True
    if text.endswith(":") and "\n" not in text:
        return True
    return False


def _fallback_reply_from_messages(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            content = message.content
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list):
                parts: list[str] = []
                for block in content:
                    if isinstance(block, str):
                        parts.append(block)
                    elif isinstance(block, dict) and "text" in block:
                        parts.append(str(block["text"]))
                return "\n".join(parts).strip()
    return ""


def finalize(state: ChatState) -> dict[str, Any]:
    structured = get_answer_model().with_structured_output(AnswerPayload)
    result = structured.invoke(
        list(state["messages"]) + [HumanMessage(content=FINAL_ANSWER_PROMPT)]
    )
    payload = result if isinstance(result, AnswerPayload) else AnswerPayload.model_validate(result)

    known = dict(state.get("known_by_id") or {})
    citations = filter_citations(list(payload.citations), known=known)
    searched_ids = list(state.get("searched_ids") or [])
    if not citations and searched_ids:
        citations = [
            ChatCitation(article_id=aid, title=known[aid].title, url=known[aid].url)
            for aid in searched_ids
            if aid in known and known[aid].url
        ][:10]

    reply = (payload.reply or "").strip()
    if not reply:
        reply = _fallback_reply_from_messages(list(state.get("messages") or []))
    if citations and _reply_looks_like_empty_list_intro(reply):
        listed = "\n".join(f"- {c.title}" for c in citations if c.title)
        if listed:
            reply = f"{reply.rstrip()}\n{listed}"

    return {
        "refused": False,
        "reply": reply,
        "citations": citations,
    }


def build_chat_graph() -> Any:
    # ty: LangGraph StateT bound doesn't yet accept TypedDict+NotRequired forms.
    graph = StateGraph(ChatState)  # ty: ignore[invalid-argument-type]
    graph.add_node("classify", classify)
    graph.add_node("refuse", refuse)
    graph.add_node("agent", agent)
    graph.add_node("tools", run_tools)
    graph.add_node("finalize", finalize)

    graph.add_edge(START, "classify")
    graph.add_conditional_edges("classify", route_after_classify, ["refuse", "agent"])
    graph.add_edge("refuse", END)
    graph.add_conditional_edges("agent", route_after_agent, ["tools", "finalize"])
    graph.add_edge("tools", "agent")
    graph.add_edge("finalize", END)
    return graph.compile()


chat_graph = build_chat_graph()
