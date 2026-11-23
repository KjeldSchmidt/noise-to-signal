"""LangGraph: prefs → context → evaluate → persist."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from n2s_api import BriefCompleteRequest, BriefItemUpsert
from n2s_preferences import get_preference_client
from n2s_web_client import complete_brief, get_brief_user_context

from llm_model import get_brief_model
from prompts import BRIEF_SYSTEM, apply_theme_affinity_scores, build_evaluate_user_message
from schemas import BriefSelection
from state import BriefState

logger = logging.getLogger(__name__)

MAX_BRIEF_ITEMS = 8


def fetch_preferences(state: BriefState) -> dict[str, Any]:
    client = get_preference_client()
    if client is None:
        return {"preferences": []}
    prefs = client.retrieve_preferences(state["user_id"], top_k=12)
    return {"preferences": prefs}


def load_user_context(state: BriefState) -> dict[str, Any]:
    ctx = get_brief_user_context(state["user_id"])
    affinities = [(a.slug, float(a.weight)) for a in ctx.theme_affinities]
    candidates = apply_theme_affinity_scores(list(ctx.candidates), affinities)
    return {"context": ctx, "candidates": candidates}


def evaluate(state: BriefState) -> dict[str, Any]:
    context = state.get("context")
    candidates = list(state.get("candidates") or [])
    if context is None or not candidates:
        return {"selected": [], "error": state.get("error") or "no candidates"}

    allowed = {c.article_id for c in candidates}
    model = get_brief_model().with_structured_output(BriefSelection)
    message = build_evaluate_user_message(
        preferences=list(state.get("preferences") or []),
        context=context,
        candidates=candidates,
    )
    try:
        result = model.invoke([SystemMessage(content=BRIEF_SYSTEM), HumanMessage(content=message)])
    except Exception as exc:
        logger.exception("brief evaluate failed")
        # Fallback: top Stories-scored candidates
        selected = [
            {
                "article_id": c.article_id,
                "rank": i,
                "score": min(0.95, max(0.4, c.score if c.score <= 1 else 0.7)),
                "reason": "High-impact story matching your feeds.",
            }
            for i, c in enumerate(candidates[:MAX_BRIEF_ITEMS], start=1)
        ]
        return {"selected": selected, "error": f"evaluate fallback: {exc}"}

    picks: list[dict[str, Any]] = []
    seen: set[int] = set()
    for pick in sorted(result.items, key=lambda p: p.rank):
        if pick.article_id not in allowed or pick.article_id in seen:
            continue
        seen.add(pick.article_id)
        picks.append(
            {
                "article_id": pick.article_id,
                "rank": len(picks) + 1,
                "score": float(pick.score),
                "reason": pick.reason.strip()[:400],
            }
        )
        if len(picks) >= MAX_BRIEF_ITEMS:
            break

    if not picks:
        picks = [
            {
                "article_id": c.article_id,
                "rank": i,
                "score": 0.65,
                "reason": "Selected from top stories for your feeds.",
            }
            for i, c in enumerate(candidates[:MAX_BRIEF_ITEMS], start=1)
        ]
    return {"selected": picks, "error": ""}


def persist(state: BriefState) -> dict[str, Any]:
    selected = list(state.get("selected") or [])
    brief_id = int(state["brief_id"])
    user_id = int(state["user_id"])
    if not selected:
        complete_brief(
            BriefCompleteRequest(
                brief_id=brief_id,
                user_id=user_id,
                status="failed",
                error=(state.get("error") or "no items selected")[:2000],
                items=[],
            )
        )
        return {}

    complete_brief(
        BriefCompleteRequest(
            brief_id=brief_id,
            user_id=user_id,
            status="ready",
            items=[
                BriefItemUpsert(
                    article_id=int(row["article_id"]),
                    rank=int(row["rank"]),
                    score=float(row["score"]),
                    reason=str(row.get("reason") or ""),
                )
                for row in selected
            ],
        )
    )
    return {}


def build_brief_graph() -> Any:
    # ty: LangGraph StateT bound doesn't yet accept TypedDict+NotRequired forms.
    graph = StateGraph(BriefState)  # ty: ignore[invalid-argument-type]
    graph.add_node("fetch_preferences", fetch_preferences)
    graph.add_node("load_user_context", load_user_context)
    graph.add_node("evaluate", evaluate)
    graph.add_node("persist", persist)
    graph.add_edge(START, "fetch_preferences")
    graph.add_edge("fetch_preferences", "load_user_context")
    graph.add_edge("load_user_context", "evaluate")
    graph.add_edge("evaluate", "persist")
    graph.add_edge("persist", END)
    return graph.compile()


brief_graph = build_brief_graph()
