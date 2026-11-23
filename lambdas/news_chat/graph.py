"""LangGraph news chat: classify → (refuse | agent ↔ tools → finalize)."""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from n2s_api import ChatCitation

from llm_model import get_answer_model, get_classifier_model
from prompts import (
    ANSWER_SYSTEM,
    CLASSIFIER_SYSTEM,
    REFUSAL_COPY,
    assemble_data_block,
    history_as_text,
    scope_hint_from_parts,
)
from schemas import AnswerPayload, RefusalReason, ScopeDecision
from state import ChatState
from tools import CHAT_TOOLS, collect_known_articles, filter_citations

MAX_TOOL_ROUNDS = 2

FINAL_ANSWER_PROMPT = (
    "Provide your final answer now. Use the search_articles results and "
    "page DATA as evidence. List any article titles in the reply text "
    "(not only in citations). Populate citations with article_id/title/url "
    "copied from DATA lines — only real article_id values that appear in "
    "DATA. If you found no articles, say so plainly."
)

_tool_node = ToolNode(CHAT_TOOLS)


def _baseline_user_message(state: ChatState) -> str:
    data = assemble_data_block(list(state.get("chunks") or []))
    return (
        f"{scope_hint_from_parts(state['scope'], state.get('scope_id'))}\n\n"
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


def agent(state: ChatState) -> dict[str, Any]:
    model = get_answer_model().bind_tools(CHAT_TOOLS)
    response = model.invoke(state["messages"])
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
