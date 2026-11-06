# news_parser

SQS-triggered worker: receives `FeedItem` messages, applies enrichment (stub for now), upserts `Article` via Django `POST /api/internal/articles/`.

**TODO:** enrich articles with coarse location (~city / ~50km) so the web app can match user locations of interest — https://github.com/KjeldSchmidt/noise-to-signal/issues/2
