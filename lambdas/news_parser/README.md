# news_parser

SQS-triggered worker: receives `FeedItem` messages, enriches them, upserts `Article` via Django `POST /api/internal/articles/`.

## Enrichment (phase 1)

1. Normalize `title` / `summary` to plain text (unescape HTML, strip tags, collapse whitespace).
2. Embed `title + summary` with **Cohere Embed Multilingual v3** on Bedrock (`cohere.embed-multilingual-v3`, `input_type=clustering`).
3. Upsert article + embedding; the web API assigns **near-dup** / **story thread** links.

No article-body scraping in this phase (RSS text only). Failures (including Bedrock errors) report SQS `batchItemFailures` so the message retries.

## Prerequisites

- Bedrock model access enabled for `cohere.embed-multilingual-v3` in the worker region (or set `BEDROCK_REGION`).
- IAM `bedrock:InvokeModel` on that model (Terraform: `invoke_bedrock = true` on the worker).
- Postgres with `pgvector` (`CREATE EXTENSION vector`) on the web DB.

## Env

| Variable | Purpose |
|----------|---------|
| `WEB_API_BASE_URL` | Public web origin |
| `INTERNAL_API_TOKEN` | Bearer for `/api/internal/*` |
| `BEDROCK_REGION` | Optional Bedrock region override |

## Story threads (web-side after upsert)

| Lane | Threshold | Window | Meaning |
|------|-----------|--------|---------|
| Near-dup | cosine ≥ 0.92 | ±48h | Same piece, other outlets |
| Story thread | cosine ≥ 0.78 vs open centroid | activity within 45 days | Evolving event timeline |

See also [infrastructure/README.md](../../infrastructure/README.md) (pgvector + Bedrock notes).

**TODO:** coarse location enrichment for `LocationOfInterest` — https://github.com/KjeldSchmidt/noise-to-signal/issues/2
