"""LangGraph enrich pipeline: normalize → embed ∥ extract_place → upsert."""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph
from n2s_api import ArticleUpsert

from embed import EMBEDDING_MODEL_ID, build_embed_input, embed_text
from extract import extract_place_and_themes
from n2s_web_client import geocode_search, list_themes, upsert_article
from state import EnrichState
from textutil import clean_text

logger = logging.getLogger(__name__)

_theme_slug_cache: list[str] | None = None


def _active_theme_slugs() -> list[str]:
    global _theme_slug_cache
    if _theme_slug_cache is None:
        _theme_slug_cache = [t.slug for t in list_themes()]
    return _theme_slug_cache


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
    """Best-effort geo + themes; never raises (soft-fail to global)."""
    out: dict[str, Any] = {
        "geo_level": "global",
        "place_label": "",
        "country_code": "",
        "admin1": "",
        "locality": "",
        "latitude": None,
        "longitude": None,
        "geo_confidence": None,
        "theme_slugs": [],
    }
    title = state["title"]
    summary = state["summary"]
    try:
        extracted = extract_place_and_themes(
            title=title,
            summary=summary,
            theme_slugs=_active_theme_slugs(),
        )
    except Exception:
        logger.exception("Place/theme extraction failed; using global")
        return out

    out["theme_slugs"] = list(extracted.get("theme_slugs") or [])
    out["geo_confidence"] = extracted.get("geo_confidence")
    place_query = (extracted.get("place_query") or "").strip()
    scope = extracted.get("geo_scope") or "global"
    if not place_query or scope == "global":
        return out

    try:
        hits = geocode_search(place_query, limit=1, scope_hint=scope)
    except Exception:
        logger.exception("Geocode failed for %r; keeping global", place_query)
        return out
    if not hits:
        return out

    hit = hits[0]
    out.update(
        {
            "geo_level": hit.geo_level or "global",
            "place_label": hit.label or "",
            "country_code": hit.country_code or "",
            "admin1": hit.admin1 or "",
            "locality": hit.locality or "",
            "latitude": hit.latitude,
            "longitude": hit.longitude,
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
        geo_level=state.get("geo_level") or "global",
        place_label=state.get("place_label") or "",
        country_code=state.get("country_code") or "",
        admin1=state.get("admin1") or "",
        locality=state.get("locality") or "",
        latitude=state.get("latitude"),
        longitude=state.get("longitude"),
        geo_confidence=state.get("geo_confidence"),
        theme_slugs=list(state.get("theme_slugs") or []),
    )
    result = upsert_article(article)
    return {
        "created": result.created,
        "article_id": result.article_id,
        "story_thread_id": result.story_thread_id,
    }


def build_graph():
    builder = StateGraph(EnrichState)
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
