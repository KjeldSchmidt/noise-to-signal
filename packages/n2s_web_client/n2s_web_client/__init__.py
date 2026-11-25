"""HTTP client for Django /api/internal/* (worker Lambdas)."""

from n2s_web_client.client import (
    complete_brief,
    export_article_embeddings,
    geocode_search,
    get_brief_user_context,
    get_story_thread_summary_context,
    ingest_feed_items,
    iter_article_embeddings,
    list_feeds,
    list_themes,
    search_articles,
    update_feed_poll_state,
    update_story_thread_summary,
    upsert_article,
)

__all__ = [
    "complete_brief",
    "export_article_embeddings",
    "geocode_search",
    "get_brief_user_context",
    "get_story_thread_summary_context",
    "ingest_feed_items",
    "iter_article_embeddings",
    "list_feeds",
    "list_themes",
    "search_articles",
    "update_feed_poll_state",
    "update_story_thread_summary",
    "upsert_article",
]
