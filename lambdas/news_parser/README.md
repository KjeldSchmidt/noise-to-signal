# news_parser

SQS-triggered worker: receives `FeedItem` messages, enriches them via a **LangGraph** pipeline, upserts `Article` via Django `POST /api/internal/articles/`.

## Enrichment graph

```
START → normalize → embed ∥ extract_place → upsert → END
```

`embed` and `extract_place` fan out from `normalize` and run in the same LangGraph superstep (concurrently). `upsert` waits for both.

1. **normalize** — plain-text `title` / `summary` (unescape HTML, strip tags, collapse whitespace).
2. **embed** — Cohere Embed Multilingual v3 on Bedrock (`cohere.embed-multilingual-v3`, `input_type=clustering`).
3. **extract_place** — Bedrock Converse (`amazon.nova-micro-v1:0` by default) for `geo_scope`, place query, allowlisted `theme_slugs`; optional `POST /api/internal/geocode/search/`. Soft-fails → `geo_level=global`.
4. **upsert** — article + embedding + place + themes; web API assigns near-dup / story thread links.

No article-body scraping in this phase (RSS text only). Embedding / hard failures report SQS `batchItemFailures`; geo/theme soft-fails.

## LangSmith

When `langsmith_agent_id` is set on the worker in Terraform, Lambda gets agent-based tracing:

| Variable | Source |
|----------|--------|
| `LANGSMITH_API_KEY` | Secrets Manager `noise-to-signal/<env>/langsmith` (via `just upsert-langsmith`) |
| `LANGSMITH_TRACING` | `true` |
| `LANGSMITH_ENDPOINT` | EU endpoint by default |
| `LANGSMITH_AGENT_ID` | Worker config (`news-parser`) |
| `LANGSMITH_AGENT_ENVIRONMENT` | `development` (dev) / `production` (prod) |

Do **not** set `LANGSMITH_PROJECT` on this process (conflicts with agent addressing). Create the LangSmith agent `news-parser` once in the UI before expecting traces.

## Prerequisites

- Bedrock model access for `cohere.embed-multilingual-v3` and the extract model (default Nova Micro).
- IAM invoke/converse on those models (Terraform: `invoke_bedrock = true`).
- Postgres with `pgvector`; migrated theme seed (`0005_article_place_themes`).
- LangSmith secret upserted before app apply if tracing is enabled: `APP_ENV=dev just upsert-langsmith`.

## Env

| Variable | Purpose |
|----------|---------|
| `WEB_API_BASE_URL` | Public web origin |
| `INTERNAL_API_TOKEN` | Bearer for `/api/internal/*` |
| `BEDROCK_REGION` | Optional Bedrock region override |
| `BEDROCK_EXTRACT_MODEL_ID` | Optional; default `amazon.nova-micro-v1:0` |
| `LANGSMITH_*` | See LangSmith section (when enabled) |

## Place matching vs `LocationOfInterest`

Matching is **hierarchical containment**, not “distance to country centroid”:

| Article | User LOI | Result |
|---------|----------|--------|
| Germany (country) | Cologne | match (containment) |
| NRW (admin1) | Cologne in NRW | match |
| Cologne (locality) | Cologne / nearby ≤ ~50 km | strong match |
| Cologne | Germany (country-only LOI) | weaker upward match |
| global | any | no geo boost |

Helper: `news.services.places.places_match` (theme ranking / prefs are out of scope for this slice).

## Story threads (web-side after upsert)

| Lane | Threshold | Window | Meaning |
|------|-----------|--------|---------|
| Near-dup | cosine ≥ 0.92 | ±48h | Same piece, other outlets |
| Story thread | cosine ≥ 0.78 vs open centroid | activity within 45 days | Evolving event timeline |

See also [infrastructure/README.md](../../infrastructure/README.md).
