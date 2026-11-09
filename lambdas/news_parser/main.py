"""news_parser — SQS-triggered enricher (embed → Article upsert)."""

from __future__ import annotations

import logging
from typing import Any

from n2s_api import ArticleUpsert, FeedItem

from embed import EMBEDDING_MODEL_ID, build_embed_input, embed_text
from n2s_web_client import upsert_article
from textutil import clean_text

logger = logging.getLogger(__name__)


def enrich_feed_item(item: FeedItem) -> ArticleUpsert:
    """Normalize text and embed title+summary via Bedrock Cohere."""
    # TODO: enrich with coarse location (~city / ~50km) for matching user
    # LocationOfInterest preferences — https://github.com/KjeldSchmidt/noise-to-signal/issues/2
    title = clean_text(item.title)[:300]
    summary = clean_text(item.description)
    embedding = embed_text(build_embed_input(title=title, summary=summary))
    return ArticleUpsert(
        feed_id=item.feed_id,
        url=item.link,
        title=title,
        summary=summary,
        published_at=item.published_at,
        image_url=item.thumbnail,
        embedding=embedding,
        embedding_model=EMBEDDING_MODEL_ID,
    )


def process_feed_item(item: FeedItem) -> dict[str, Any]:
    article = enrich_feed_item(item)
    result = upsert_article(article)
    return {
        "feed_id": item.feed_id,
        "url": item.link,
        "created": result.created,
        "article_id": result.article_id,
        "story_thread_id": result.story_thread_id,
    }


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """SQS event source mapping entrypoint."""
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
            if message_id:
                batch_failures.append({"itemIdentifier": message_id})

    response: dict[str, Any] = {
        "ok": len(batch_failures) == 0,
        "processed": len(results),
        "results": results,
    }
    if batch_failures:
        response["batchItemFailures"] = batch_failures
    return response
