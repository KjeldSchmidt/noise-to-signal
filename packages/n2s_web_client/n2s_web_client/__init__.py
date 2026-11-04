"""HTTP client for Django /api/internal/* (worker Lambdas)."""

from n2s_web_client.client import ingest_feed_items, list_feeds, upsert_article

__all__ = ["ingest_feed_items", "list_feeds", "upsert_article"]
