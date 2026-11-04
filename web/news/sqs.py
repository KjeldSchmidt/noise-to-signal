"""SQS helpers for enqueueing new feed items to news_parser."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.conf import settings

if TYPE_CHECKING:
    from n2s_api import FeedItem

logger = logging.getLogger(__name__)


def enqueue_feed_items(items: list[FeedItem]) -> int:
    """Send one SQS message per item. Returns number successfully sent."""
    queue_url = (getattr(settings, "FEED_ITEMS_QUEUE_URL", None) or "").strip()
    if not queue_url:
        logger.warning("FEED_ITEMS_QUEUE_URL unset — skipping enqueue of %s items", len(items))
        return 0
    if not items:
        return 0

    import boto3

    client = boto3.client("sqs")
    sent = 0
    for item in items:
        client.send_message(QueueUrl=queue_url, MessageBody=item.model_dump_json())
        sent += 1
    return sent
