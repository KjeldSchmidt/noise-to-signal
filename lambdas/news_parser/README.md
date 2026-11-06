# news_parser

SQS-triggered worker: receives `FeedItem` messages, enriches them, upserts `Article` via Django `POST /api/internal/articles/`.

**Current enrichment:** normalize `title` / `summary` to plain text (unescape HTML entities, strip all tags, collapse whitespace).

**TODO:** enrich articles with coarse location (~city / ~50km) so the web app can match user locations of interest — https://github.com/KjeldSchmidt/noise-to-signal/issues/2
