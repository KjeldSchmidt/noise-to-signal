"""LangGraph enrich pipeline: normalize → embed ∥ extract_place → upsert."""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph
from n2s_api import ArticleUpsert
from n2s_web_client import geocode_search, list_themes, upsert_article

from embed import EMBEDDING_MODEL_ID, build_embed_input, embed_text
from extract import extract_place_and_themes
from llm_model import EXTRACT_MODEL_ID
from place_attach import decide_attach
from state import EnrichState
from textutil import clean_text

logger = logging.getLogger(__name__)

_theme_cache: list[dict[str, str]] | None = None


def _active_themes() -> list[dict[str, str]]:
    global _theme_cache
    if _theme_cache is None:
        _theme_cache = [{"slug": t.slug, "label": t.label} for t in list_themes()]
    return _theme_cache


def normalize(state: EnrichState) -> dict[str, Any]:
    return {
        "title": clean_text(state["raw_title"])[:300],
        "summary": clean_text(state["raw_description"]),
    }


def embed(state: EnrichState) -> dict[str, Any]:
    text = build_embed_input(title=state["title"], summary=state["summary"])
    return {
        "embedding": embed_text(text),
        "embedding_model": EMBEDDING_MODEL_ID,
    }


def extract_place(state: EnrichState) -> dict[str, Any]:
    """Extract place/themes via Bedrock; LLM failures raise (SQS retry / DLQ).

    Geocode transport failures soft-fail to global with enrichment_status=degraded.
    Policy rejects (ambiguous / weak / mismatch) leave global with status=ok.
    """
    title = state["title"]
    summary = state["summary"]
    # LLM / structured-output errors must propagate — do not soft-fail to "empty".
    extracted = extract_place_and_themes(
        title=title,
        summary=summary,
        themes=_active_themes(),
    )

    out: dict[str, Any] = {
        "geo_level": "global",
        "place_label": "",
        "country_code": "",
        "admin1": "",
        "locality": "",
        "latitude": None,
        "longitude": None,
        "geo_confidence": None,
        "theme_slugs": list(extracted.get("theme_slugs") or []),
        "suggested_themes": list(extracted.get("suggested_themes") or []),
        "story_label": (extracted.get("story_label") or "")[:120],
        "extract_model": EXTRACT_MODEL_ID,
        "enrichment_status": "ok",
    }

    place_query = (extracted.get("place_query") or "").strip()
    country_hint = (extracted.get("country_hint") or "").strip()
    mention_basis = (extracted.get("mention_basis") or "none").strip().lower()
    scope = extracted.get("geo_scope") or "global"
    # Geocode only explicit candidates. Skip "global" as scope_hint —
    # Nominatim would otherwise force geo_level=global even for real countries.
    if mention_basis != "explicit" or not place_query or not country_hint:
        return out
    scope_hint = "" if scope == "global" else str(scope)

    try:
        hits = geocode_search(place_query, limit=5, scope_hint=scope_hint)
    except Exception:
        logger.exception("Geocode failed for %r; keeping global (degraded)", place_query)
        out["enrichment_status"] = "degraded"
        return out
    if not hits:
        logger.warning("Geocode returned no hits for %r; degraded", place_query)
        out["enrichment_status"] = "degraded"
        return out

    decision = decide_attach(
        place_query=place_query,
        country_hint=country_hint,
        geo_scope=str(scope),
        hits=hits,
    )
    if not decision.keep or decision.hit is None:
        logger.info(
            "Discarding place attach for %r (hint=%s): %s",
            place_query,
            country_hint,
            decision.reason,
        )
        return out

    hit = decision.hit
    out.update(
        {
            "geo_level": hit.geo_level or "global",
            "place_label": hit.label or "",
            "country_code": hit.country_code or "",
            "admin1": hit.admin1 or "",
            "locality": hit.locality or "",
            "latitude": hit.latitude,
            "longitude": hit.longitude,
            "geo_confidence": 1.0,
            "enrichment_status": "ok",
        }
    )
    return out


def upsert(state: EnrichState) -> dict[str, Any]:
    article = ArticleUpsert(
        feed_id=state["feed_id"],
        url=state["url"],
        title=state["title"],
        summary=state["summary"],
        published_at=state["published_at"],
        image_url=state["image_url"],
        embedding=state["embedding"],
        embedding_model=state["embedding_model"],
        enrichment_status=state.get("enrichment_status") or "",
        extract_model=state.get("extract_model") or "",
        geo_level=state.get("geo_level") or "global",
        place_label=state.get("place_label") or "",
        country_code=state.get("country_code") or "",
        admin1=state.get("admin1") or "",
        locality=state.get("locality") or "",
        latitude=state.get("latitude"),
        longitude=state.get("longitude"),
        geo_confidence=state.get("geo_confidence"),
        story_label=state.get("story_label") or "",
        theme_slugs=list(state.get("theme_slugs") or []),
        suggested_themes=list(state.get("suggested_themes") or []),
    )
    result = upsert_article(article)
    return {
        "created": result.created,
        "article_id": result.article_id,
        "story_thread_id": result.story_thread_id,
    }


def build_graph():
    # ty: LangGraph StateT bound doesn't yet accept TypedDict+NotRequired forms.
    builder = StateGraph(EnrichState)  # ty: ignore[invalid-argument-type]
    builder.add_node("normalize", normalize)
    builder.add_node("embed", embed)
    builder.add_node("extract_place", extract_place)
    builder.add_node("upsert", upsert)

    builder.add_edge(START, "normalize")
    builder.add_edge("normalize", "embed")
    builder.add_edge("normalize", "extract_place")
    builder.add_edge(["embed", "extract_place"], "upsert")
    builder.add_edge("upsert", END)
    return builder.compile()


enrich_graph = build_graph()
