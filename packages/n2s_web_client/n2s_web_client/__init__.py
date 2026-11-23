"""HTTP client for Django /api/internal/* (worker Lambdas)."""

from n2s_web_client.client import (
    complete_brief,
    geocode_search,
    get_brief_user_context,
    ingest_feed_items,
    list_feeds,
    list_themes,
    search_articles,
    update_feed_poll_state,
    upsert_article,
)

__all__ = [
    "complete_brief",
    "geocode_search",
    "get_brief_user_context",
    "ingest_feed_items",
    "list_feeds",
    "list_themes",
    "search_articles",
    "update_feed_poll_state",
    "upsert_article",
]
