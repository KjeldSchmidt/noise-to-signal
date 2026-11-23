"""Scope classifier + grounded answer pipeline with optional search tool."""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from n2s_api import (
    ChatCitation,
    ChatWorkerRequest,
    ChatWorkerResponse,
    ContextChunk,
)
from pydantic import BaseModel, Field

from llm_model import get_answer_model, get_classifier_model
from prompts import (
    ANSWER_SYSTEM,
    CLASSIFIER_SYSTEM,
    REFUSAL_COPY,
    assemble_data_block,
    history_as_text,
    scope_hint,
)
from tools import collect_known_articles, filter_citations, make_search_articles_tool

RefusalReason = Literal["ok", "off_topic", "injection"]
MAX_TOOL_ROUNDS = 2


class ScopeDecision(BaseModel):
    allowed: bool
    reason: RefusalReason = Field(description="ok if allowed; otherwise off_topic or injection")


class AnswerPayload(BaseModel):
    reply: str = Field(description="Concise answer for the user")
    citations: list[ChatCitation] = Field(
        default_factory=list,
        description=(
            "Articles you relied on from DATA / search results. "
            "Only include article_id values that appeared in the provided articles."
        ),
    )


def classify_request(req: ChatWorkerRequest) -> ScopeDecision:
    structured = get_classifier_model().with_structured_output(ScopeDecision)
    user = (
        f"{scope_hint(req)}\n"
        f"history:\n{history_as_text(req.history)}\n\n"
        f"user_message:\n{req.message}"
    )
    result = structured.invoke(
        [
            SystemMessage(content=CLASSIFIER_SYSTEM),
            HumanMessage(content=user),
        ]
    )
    if isinstance(result, ScopeDecision):
        return result
    return ScopeDecision.model_validate(result)


def _message_content_text(content: Any) -> str:
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
    return str(content).strip()


def _baseline_user_message(req: ChatWorkerRequest) -> str:
    data = assemble_data_block(list(req.chunks))
    return (
        f"{scope_hint(req)}\n\n"
        f"{data}\n\n"
        f"Conversation so far:\n{history_as_text(req.history)}\n\n"
        f"User question:\n{req.message}"
    )


def answer_request(req: ChatWorkerRequest) -> tuple[str, list[ChatCitation]]:
    known = collect_known_articles(list(req.chunks))
    exclude_ids = list(known.keys())

    def on_results(chunks: list[ContextChunk]) -> None:
        known.update(collect_known_articles(chunks))

    search_tool = make_search_articles_tool(
        user_id=req.user_id,
        exclude_article_ids=exclude_ids,
        on_results=on_results,
    )
    tools_by_name = {search_tool.name: search_tool}

    tool_model = get_answer_model().bind_tools([search_tool])
    messages: list[Any] = [
        SystemMessage(content=ANSWER_SYSTEM),
        HumanMessage(content=_baseline_user_message(req)),
    ]

    for _ in range(MAX_TOOL_ROUNDS):
        ai = tool_model.invoke(messages)
        messages.append(ai)
        tool_calls = getattr(ai, "tool_calls", None) or []
        if not tool_calls:
            break
        for call in tool_calls:
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", "")
            call_id = (call.get("id") if isinstance(call, dict) else getattr(call, "id", "")) or ""
            args = call.get("args") if isinstance(call, dict) else getattr(call, "args", {})
            tool = tools_by_name.get(str(name))
            if tool is None:
                tool_output = f"Unknown tool: {name}"
            else:
                tool_output = str(tool.invoke(args or {}))
            messages.append(ToolMessage(content=tool_output, tool_call_id=str(call_id)))

    structured = get_answer_model().with_structured_output(AnswerPayload)
    final_messages = list(messages) + [
        HumanMessage(
            content=(
                "Provide your final answer now. Use the search_articles results and "
                "page DATA as evidence. Populate citations with article_id/title/url "
                "only for articles you actually used (ids must appear in DATA)."
            )
        )
    ]
    result = structured.invoke(final_messages)
    payload = result if isinstance(result, AnswerPayload) else AnswerPayload.model_validate(result)
    citations = filter_citations(list(payload.citations), known=known)
    reply = (payload.reply or "").strip()
    if not reply and isinstance(messages[-1], AIMessage):
        reply = _message_content_text(messages[-1].content)
    return reply, citations


def run_chat(req: ChatWorkerRequest) -> ChatWorkerResponse:
    decision = classify_request(req)
    if not decision.allowed:
        reason: RefusalReason = (
            decision.reason if decision.reason in ("off_topic", "injection") else "off_topic"
        )
        return ChatWorkerResponse(
            refused=True,
            reason=reason,
            reply="",
            message=REFUSAL_COPY.get(reason) or REFUSAL_COPY["off_topic"],
            citations=[],
        )

    reply, citations = answer_request(req)
    return ChatWorkerResponse(
        refused=False,
        reason="ok",
        reply=reply,
        message="",
        citations=citations,
    )
