"""LangGraph tools for news_chat (InjectedState + Command updates)."""

from __future__ import annotations

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


class SearchArticlesArgs(BaseModel):
    query: str = Field(
        description=("Short search phrase (keywords or topic). Do not paste the full user message.")
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


def _search_content(
    *,
    query: str,
    user_id: int,
    exclude_article_ids: list[int],
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
    else:
        embed_error = ""

    try:
        results = client_search_articles(
            ArticleSearchRequest(
                query=text,
                user_id=user_id,
                embedding=embedding,
                limit=10,
                exclude_article_ids=exclude_article_ids,
            )
        )
    except Exception as exc:  # noqa: BLE001
        return f"search_articles failed: {exc}", []

    if not results:
        return f"No matching articles found.{embed_error}", []
    return assemble_data_block(results) + embed_error, list(results)


@tool("search_articles", args_schema=SearchArticlesArgs)
def search_articles(
    query: str,
    state: Annotated[ChatState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """
    Search the user's news database by title/summary text and semantic similarity.
    Use when the page context is insufficient. Pass a short search phrase, not the
    full chat message.
    """
    known = dict(state.get("known_by_id") or {})
    content, results = _search_content(
        query=query,
        user_id=int(state["user_id"]),
        exclude_article_ids=list(known.keys()),
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


CHAT_TOOLS = [search_articles]
