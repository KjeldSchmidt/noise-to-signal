"""Scope classifier + grounded answer pipeline."""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from n2s_api import ChatWorkerRequest, ChatWorkerResponse
from pydantic import BaseModel, Field

from llm_model import get_answer_model, get_classifier_model
from prompts import (
    ANSWER_SYSTEM,
    CLASSIFIER_SYSTEM,
    REFUSAL_COPY,
    assemble_data_block,
    history_as_text,
    scope_hint,
    topic_digest,
)

RefusalReason = Literal["ok", "off_topic", "injection"]


class ScopeDecision(BaseModel):
    allowed: bool
    reason: RefusalReason = Field(description="ok if allowed; otherwise off_topic or injection")


def classify_request(req: ChatWorkerRequest) -> ScopeDecision:
    structured = get_classifier_model().with_structured_output(ScopeDecision)
    user = (
        f"{scope_hint(req)}\n"
        f"topic_digest:\n{topic_digest(list(req.chunks))}\n\n"
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


def answer_request(req: ChatWorkerRequest) -> str:
    data = assemble_data_block(list(req.chunks))
    user = (
        f"{scope_hint(req)}\n\n"
        f"{data}\n\n"
        f"Conversation so far:\n{history_as_text(req.history)}\n\n"
        f"User question:\n{req.message}"
    )
    result = get_answer_model().invoke(
        [
            SystemMessage(content=ANSWER_SYSTEM),
            HumanMessage(content=user),
        ]
    )
    content = getattr(result, "content", result)
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and "text" in block:
                parts.append(str(block["text"]))
        return "\n".join(parts).strip()
    return str(content).strip()


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
        )

    reply = answer_request(req)
    return ChatWorkerResponse(
        refused=False,
        reason="ok",
        reply=reply,
        message="",
    )
