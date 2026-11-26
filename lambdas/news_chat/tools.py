"""LangGraph tools for news_chat (InjectedState + Command updates)."""

from __future__ import annotations

import logging
from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from n2s_api import ArticleSearchRequest, ChatCitation, ContextChunk
from n2s_web_client.client import search_articles as client_search_articles
from pydantic import BaseModel, Field

from embed import embed_text
from prompts import assemble_data_block
from state import ChatState

logger = logging.getLogger(__name__)

# Search query is a short keyword phrase (not the full chat message). Cap length
# in logs so accidental long args stay bounded; do not log preference text.
_LOG_QUERY_MAX = 120


class SearchArticlesArgs(BaseModel):
    query: str = Field(
        description=("Short search phrase (keywords or topic). Do not paste the full user message.")
    )
    country_code: str | None = Field(
        default=None,
        description=(
            "Optional ISO 3166-1 alpha-2 country filter on article place "
            "(e.g. 'de' for Germany). Use for geo questions like German news."
        ),
    )
    published_after: str | None = Field(
        default=None,
        description=(
            "Optional ISO-8601 lower bound on published_at "
            "(e.g. start of today UTC or now-minus-24h). Use for 'today' / recent."
        ),
    )


class SavePreferenceArgs(BaseModel):
    text: str = Field(
        description=(
            "Short free-form reading preference to remember "
            "(e.g. 'less US election horse-race, more policy analysis')."
        )
    )


def collect_known_articles(chunks: list[ContextChunk]) -> dict[int, ContextChunk]:
    known: dict[int, ContextChunk] = {}
    for chunk in chunks:
        if chunk.article_id is not None:
            known[chunk.article_id] = chunk
    return known


def filter_citations(
    citations: list[ChatCitation],
    *,
    known: dict[int, ContextChunk],
) -> list[ChatCitation]:
    """Keep citations whose article_id appears in known chunks; fill title/url from known."""
    out: list[ChatCitation] = []
    seen: set[int] = set()
    for raw in citations:
        article_id = raw.article_id
        if article_id in seen:
            continue
        chunk = known.get(article_id)
        if chunk is None:
            continue
        title = (raw.title or chunk.title or "").strip() or chunk.title
        url = (raw.url or chunk.url or "").strip() or chunk.url
        if not url:
            continue
        out.append(ChatCitation(article_id=article_id, title=title, url=url))
        seen.add(article_id)
    return out


def _log_search_call(
    *,
    user_id: int,
    query: str,
    country_code: str | None,
    published_after: str | None,
    hit_count: int,
    article_ids: list[int],
    country_codes: list[str],
    embed_ok: bool,
    error: str | None = None,
) -> None:
    """CloudWatch-friendly tool audit — filters + ids only (no summaries/prefs)."""
    q = query if len(query) <= _LOG_QUERY_MAX else f"{query[:_LOG_QUERY_MAX]}…"
    if error:
        logger.info(
            "search_articles user_id=%s query=%r country_code=%s published_after=%s "
            "embed_ok=%s error=%s",
            user_id,
            q,
            country_code,
            published_after,
            embed_ok,
            error,
        )
        return
    logger.info(
        "search_articles user_id=%s query=%r country_code=%s published_after=%s "
        "embed_ok=%s hits=%s article_ids=%s result_country_codes=%s",
        user_id,
        q,
        country_code,
        published_after,
        embed_ok,
        hit_count,
        article_ids,
        country_codes,
    )


def _search_content(
    *,
    query: str,
    user_id: int,
    exclude_article_ids: list[int],
    country_code: str | None = None,
    published_after: str | None = None,
) -> tuple[str, list[ContextChunk]]:
    text = (query or "").strip()
    if not text:
        return "No query provided.", []

    embedding: list[float] | None
    try:
        embedding = embed_text(text)
    except Exception as exc:  # noqa: BLE001 — tool should not crash the agent loop
        embedding = None
        embed_error = f" (embedding skipped: {exc})"
        embed_ok = False
    else:
        embed_error = ""
        embed_ok = True

    code = (country_code or "").strip().lower()[:2] or None
    after = (published_after or "").strip() or None

    try:
        results = client_search_articles(
            ArticleSearchRequest(
                query=text,
                user_id=user_id,
                embedding=embedding,
                limit=10,
                exclude_article_ids=exclude_article_ids,
                country_code=code,
                published_after=after,
            )
        )
    except Exception as exc:  # noqa: BLE001
        _log_search_call(
            user_id=user_id,
            query=text,
            country_code=code,
            published_after=after,
            hit_count=0,
            article_ids=[],
            country_codes=[],
            embed_ok=embed_ok,
            error=str(exc),
        )
        return f"search_articles failed: {exc}", []

    hits = list(results)
    article_ids = [c.article_id for c in hits if c.article_id is not None]
    country_codes = [(c.country_code or "") for c in hits]
    _log_search_call(
        user_id=user_id,
        query=text,
        country_code=code,
        published_after=after,
        hit_count=len(hits),
        article_ids=article_ids,
        country_codes=country_codes,
        embed_ok=embed_ok,
    )

    if not hits:
        return f"No matching articles found.{embed_error}", []
    return assemble_data_block(hits) + embed_error, hits


@tool("search_articles", args_schema=SearchArticlesArgs)
def search_articles(
    query: str,
    state: Annotated[ChatState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    country_code: str | None = None,
    published_after: str | None = None,
) -> Command:
    """
    Search the user's news database by title/summary text and semantic similarity.
    Use when the page context is insufficient, and for geo/recency questions
    (country_code + published_after). Pass a short search phrase, not the full
    chat message.
    """
    known = dict(state.get("known_by_id") or {})
    content, results = _search_content(
        query=query,
        user_id=int(state["user_id"]),
        exclude_article_ids=list(known.keys()),
        country_code=country_code,
        published_after=published_after,
    )
    found = collect_known_articles(results)
    known.update(found)
    searched = list(state.get("searched_ids") or [])
    for article_id in found:
        if article_id not in searched:
            searched.append(article_id)
    return Command(
        update={
            "known_by_id": known,
            "searched_ids": searched,
            "messages": [ToolMessage(content=content, tool_call_id=tool_call_id)],
        }
    )


def _record_preference(user_id: int, text: str) -> str:
    content = (text or "").strip()
    if not content:
        return "No preference text provided."
    try:
        from n2s_preferences import get_preference_client
    except ImportError:
        return "Preference memory is unavailable."
    client = get_preference_client()
    if client is None:
        return "Preference memory is not configured."
    try:
        client.record_preference(user_id, content[:2000])
    except Exception as exc:  # noqa: BLE001
        return f"Could not save preference: {exc}"
    # CreateEvent queues STM; USER_PREFERENCE LTM extraction is async (minutes).
    return f"Saved preference (may take a few minutes to appear in Settings): {content[:400]}"


def _list_preferences(user_id: int) -> str:
    try:
        from n2s_preferences import get_preference_client
    except ImportError:
        return "Preference memory is unavailable."
    client = get_preference_client()
    if client is None:
        return "Preference memory is not configured."
    try:
        records = client.list_preference_records(user_id)
    except Exception as exc:  # noqa: BLE001
        return f"Could not list preferences: {exc}"
    if not records:
        return "No stored preferences yet."
    lines = [f"- {r.text}" for r in records[:25]]
    return "Stored preferences:\n" + "\n".join(lines)


@tool("save_preference", args_schema=SavePreferenceArgs)
def save_preference(
    text: str,
    state: Annotated[ChatState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """
    Remember a free-form reading preference for future briefs (brief scope only).
    Call when the user states a lasting taste preference worth storing.
    Only tell the user it was saved after this tool returns success.
    """
    user_id = int(state["user_id"])
    # Preference body can be user-authored — log length only, never the text.
    logger.info(
        "save_preference user_id=%s scope=%s text_chars=%s",
        user_id,
        state.get("scope"),
        len((text or "").strip()),
    )
    if state.get("scope") != "brief":
        content = "Preference tools are only available on the daily brief chat."
    else:
        content = _record_preference(user_id, text)
    return Command(update={"messages": [ToolMessage(content=content, tool_call_id=tool_call_id)]})


@tool("list_preferences")
def list_preferences(
    state: Annotated[ChatState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """List stored free-form reading preferences (brief scope only)."""
    user_id = int(state["user_id"])
    logger.info("list_preferences user_id=%s scope=%s", user_id, state.get("scope"))
    if state.get("scope") != "brief":
        content = "Preference tools are only available on the daily brief chat."
    else:
        content = _list_preferences(user_id)
    return Command(update={"messages": [ToolMessage(content=content, tool_call_id=tool_call_id)]})


CHAT_TOOLS = [search_articles, save_preference, list_preferences]
