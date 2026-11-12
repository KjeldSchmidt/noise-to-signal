"""news_parser — SQS-triggered enricher (LangGraph: embed ∥ place → Article upsert)."""

from __future__ import annotations

import logging
from typing import Any

from n2s_api import FeedItem

from graph import enrich_graph

logger = logging.getLogger(__name__)


def process_feed_item(item: FeedItem) -> dict[str, Any]:
    """Run the enrich graph for one feed item and return a result summary."""
    final = enrich_graph.invoke(
        {
            "feed_id": item.feed_id,
            "url": item.link,
            "raw_title": item.title,
            "raw_description": item.description,
            "published_at": item.published_at,
            "image_url": item.thumbnail,
            "feed_language": item.feed_language or "",
        }
    )
    return {
        "feed_id": item.feed_id,
        "url": item.link,
        "created": final["created"],
        "article_id": final["article_id"],
        "story_thread_id": final.get("story_thread_id"),
        "geo_level": final.get("geo_level") or "global",
        "theme_slugs": list(final.get("theme_slugs") or []),
    }


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """SQS event source mapping entrypoint (ReportBatchItemFailures)."""
    records = event.get("Records") or []
    results: list[dict[str, Any]] = []
    batch_failures: list[dict[str, str]] = []

    for record in records:
        message_id = str(record.get("messageId") or "")
        try:
            item = FeedItem.model_validate_json(record.get("body") or "{}")
            if not item.link:
                raise ValueError("missing link")
            results.append(process_feed_item(item))
        except Exception:
            logger.exception("Failed to process SQS message %s", message_id)
            # Without messageId Lambda cannot retry just this record; fail the
            # whole invocation so the batch is not silently acknowledged.
            if not message_id:
                raise
            batch_failures.append({"itemIdentifier": message_id})

    return {
        "ok": len(batch_failures) == 0,
        "processed": len(results),
        "results": results,
        "batchItemFailures": batch_failures,
    }
