"""Scoped retrieval for news chat (search-ready interface)."""

from __future__ import annotations

from typing import Literal

from django.contrib.auth.models import AbstractBaseUser
from n2s_api import MAX_CHUNK_CHARS, MAX_CHUNKS, ContextChunk

from news.models import Article
from news.services.feeds import enabled_feed_ids
from news.services.ranking import rank_items
from news.services.stories_feed import thread_timeline_articles, thread_visible_in_scope

ChatRetrieveScope = Literal["brief", "thread"]


def _article_to_chunk(article: Article) -> ContextChunk:
    published = ""
    if article.published_at is not None:
        published = article.published_at.isoformat()
    summary = (article.summary or "").strip()
    if len(summary) > MAX_CHUNK_CHARS:
        summary = summary[: MAX_CHUNK_CHARS - 1] + "…"
    return ContextChunk(
        article_id=article.pk,
        title=article.title or "",
        source=article.feed.title if article.feed_id else "",
        published_at=published,
        summary=summary,
        story_label=article.story_label or "",
        impact_tier=article.impact_tier or "",
        place_label=article.place_label or "",
        url=article.url or "",
    )


def _limit_chunks(articles: list[Article]) -> list[ContextChunk]:
    return [_article_to_chunk(a) for a in articles[:MAX_CHUNKS]]


def retrieve_brief_context(user: AbstractBaseUser) -> list[ContextChunk]:
    """Articles grounding the user's current brief (ranked, else recent in-scope)."""
    ranked = rank_items(user)
    articles = [item.article for item in ranked]
    if not articles:
        feed_ids = enabled_feed_ids(user)
        if feed_ids:
            articles = list(
                Article.objects.filter(feed_id__in=feed_ids)
                .select_related("feed")
                .order_by("-published_at")[:MAX_CHUNKS]
            )
    return _limit_chunks(articles)


def retrieve_thread_context(
    user: AbstractBaseUser,
    thread_id: int,
) -> list[ContextChunk] | None:
    """
    Thread timeline chunks if visible in the user's feed scope.

    Returns None when the thread is missing or out of scope (caller → 404).
    """
    feed_ids = enabled_feed_ids(user)
    thread = thread_visible_in_scope(thread_id, feed_ids)
    if thread is None:
        return None
    articles = thread_timeline_articles(thread)
    return _limit_chunks(articles)


def retrieve(
    *,
    scope: ChatRetrieveScope,
    user: AbstractBaseUser,
    scope_id: int | None = None,
) -> list[ContextChunk] | None:
    """
    Resolve grounded context for a chat scope.

    Returns None for unauthorized / missing thread scope.
    A future ``query`` scope (embedding ANN) can plug in here without
    changing the news_chat worker contract.
    """
    if scope == "brief":
        return retrieve_brief_context(user)
    if scope == "thread":
        if scope_id is None:
            return None
        return retrieve_thread_context(user, scope_id)
    return None
