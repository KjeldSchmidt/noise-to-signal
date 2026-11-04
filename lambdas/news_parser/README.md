# news_parser

SQS-triggered worker: receives `FeedItem` messages, applies enrichment (stub for now), upserts `Article` via Django `POST /api/internal/articles/`.
