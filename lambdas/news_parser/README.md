# news_parser

SQS-triggered worker: receives `FeedItem` messages, enriches them via a **LangGraph** pipeline, upserts `Article` via Django `POST /api/internal/articles/`.

## Enrichment graph

```
START → normalize → embed ∥ extract_place → upsert → END
```

`embed` and `extract_place` fan out from `normalize` and run in the same LangGraph superstep (concurrently). `upsert` waits for both.

1. **normalize** — plain-text `title` / `summary` (unescape HTML, strip tags, collapse whitespace).
2. **embed** — LangChain `BedrockEmbeddings` for Cohere Embed Multilingual v3 (`cohere.embed-multilingual-v3`, `input_type=clustering`).
3. **extract_place** — LangChain `with_structured_output` via Bedrock Converse (`amazon.nova-micro-v1:0` by default) for `geo_scope`, place query, enum-constrained `theme_slugs` (curated catalog), free-form `suggested_themes`, and `story_label`; geocodes whenever a place query is present (`POST /api/internal/geocode/search/`). Soft-fails → `geo_level=global`.
4. **upsert** — article + embedding + place + themes; web API increments `ThemeSuggestion` counters for suggestions and assigns near-dup / story thread links.

No article-body scraping in this phase (RSS text only). Embedding / hard failures report SQS `batchItemFailures`; geo/theme soft-fails.

## LangSmith

When `langsmith_agent_id` is set on the worker in Terraform, Lambda gets agent-based tracing. The LangChain extract call appears as an LLM child run under `extract_place` (prompt + structured result), not only the node final state.

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

Threads are **optional**. Lonely articles stay unthreaded. A thread is created only when a near-dup or soft peer pair connects two+ articles (or when joining an open centroid). Extract may supply a short generic `story_label` (e.g. `Spanish Rail Crash`) used as the thread title on create.

| Lane | Threshold | Window | Meaning |
|------|-----------|--------|---------|
| Near-dup | cosine ≥ 0.92 | ±48h | Same piece, other outlets → shared thread |
| Open thread | cosine ≥ 0.78 vs centroid | 45-day activity | Join evolving event |
| Soft peer | cosine ≥ 0.78 vs unthreaded peer | 45-day window | Create thread for both |

### Story assignment lock

**SCALING HOTSPOT:** web `assign_story_thread` takes a Postgres `pg_advisory_xact_lock` so concurrent Lambda upserts cannot miss each other. Cheap at current volume; under heavy concurrent upserts this serializes linking and may queue API work. Prefer faster peer queries, `reconcile_story_threads`, or a seeker job before removing the lock (`rg "SCALING HOTSPOT"`).

Ops helpers (Django): `dissolve_singleton_threads`, `reconcile_story_threads`, `requeue_articles`.

See also [infrastructure/README.md](../../infrastructure/README.md).
