# news_parser

SQS-triggered worker: receives `FeedItem` messages, enriches them via a **LangGraph** pipeline, upserts `Article` via Django `POST /api/internal/articles/`.

## Enrichment graph

```
START → normalize → embed ∥ extract_place → upsert → END
```

`embed` and `extract_place` fan out from `normalize` and run in the same LangGraph superstep (concurrently). `upsert` waits for both.

1. **normalize** — plain-text `title` / `summary` (unescape HTML, strip tags, collapse whitespace).
2. **embed** — LangChain `BedrockEmbeddings` for Cohere Embed Multilingual v3 (`cohere.embed-multilingual-v3`, `input_type=clustering`).
3. **extract_place** — LangChain `with_structured_output` via Bedrock Converse (`eu.amazon.nova-micro-v1:0` inference profile by default) for `geo_scope`, place query, enum-constrained `theme_slugs` (curated catalog), free-form `suggested_themes`, `story_label`, and `impact_tier` / `impact_rationale`; geocodes explicit place candidates (`POST /api/internal/geocode/search/`) then applies a keep/discard attach policy. Soft geocode failures → `geo_level=global` with `enrichment_status=degraded`.
4. **upsert** — article + embedding + place + themes + impact; web API increments `ThemeSuggestion` counters for suggestions and assigns near-dup / story thread links.

No article-body scraping in this phase (RSS text only). Embedding **and extract LLM** failures raise → SQS `batchItemFailures` / DLQ. Geocode misses soft-fail with `enrichment_status=degraded` (themes/story_label/impact still saved).

## Impact tiers

User-agnostic lasting importance (not personal taste — distinct from `RelevanceFeedback`):

| Tier | Meaning |
|------|---------|
| `commercial` | Promo, deal, gift guide, affiliate-shaped |
| `ephemeral` | Short half-life; little structural weight |
| `notable` | Acute or domain-significant |
| `major` | International / lasting civic or systemic importance |

Stored on `Article.impact_tier` (+ short `impact_rationale` for admin). Later: story page / brief ranking consumers; thread rollup = max of member tiers.

## Langfuse

When `langfuse_tracing = true` on the worker in Terraform, Lambda sends LangChain/LangGraph traces to Langfuse. The extract call appears as an LLM child observation under `extract_place`.

| Variable | Source |
|----------|--------|
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | Secrets Manager `noise-to-signal/<env>/langfuse` (via `just upsert-langfuse`) |
| `LANGFUSE_BASE_URL` | From secret, else EU cloud default |
| `LANGFUSE_TRACING_ENVIRONMENT` | `development` (dev) / `production` (prod) |
| `LANGFUSE_SAMPLE_RATE` | Optional; from `langfuse_sample_rate` (e.g. `0.01`) |
| `LANGFUSE_TAGS` | Worker name (`news_parser`) |

## Prerequisites

- Bedrock model access for `cohere.embed-multilingual-v3` and the extract inference profile (default `eu.amazon.nova-micro-v1:0`).
- IAM invoke/converse on those models (Terraform: `invoke_bedrock = true`).
- Postgres with `pgvector`; migrated theme seed (`0005_article_place_themes`).
- Langfuse secret upserted before app apply if tracing is enabled: `APP_ENV=dev just upsert-langfuse`.

## Env

| Variable | Purpose |
|----------|---------|
| `WEB_API_BASE_URL` | Public web origin |
| `INTERNAL_API_TOKEN` | Bearer for `/api/internal/*` |
| `BEDROCK_REGION` | Optional Bedrock region override |
| `BEDROCK_EXTRACT_MODEL_ID` | Optional; default `eu.amazon.nova-micro-v1:0` (inference profile; bare `amazon.nova-micro-v1:0` fails on-demand) |
| `LANGFUSE_*` | See Langfuse section (when enabled) |

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

Threads are **optional**. Lonely articles stay unthreaded. A thread is created only when a near-dup or soft peer pair connects two+ articles (or when joining an open centroid). Extract may supply a short generic `story_label` (source language or English, e.g. `Spanish Rail Crash`) used as the bootstrap thread title on create; multilingual display titles come from `story_summarizer`.

| Lane | Threshold | Window | Meaning |
|------|-----------|--------|---------|
| Near-dup | cosine ≥ 0.92 | ±48h | Same piece, other outlets → shared thread |
| Open thread | cosine ≥ 0.78 vs centroid | 45-day activity | Join evolving event |
| Soft peer | cosine ≥ 0.78 vs unthreaded peer | 45-day window | Create thread for both |

### Story assignment lock

**SCALING HOTSPOT:** web `assign_story_thread` takes a Postgres `pg_advisory_xact_lock` so concurrent Lambda upserts cannot miss each other. Cheap at current volume; under heavy concurrent upserts this serializes linking and may queue API work. Prefer faster peer queries, `reconcile_story_threads`, or a seeker job before removing the lock (`rg "SCALING HOTSPOT"`).

Ops helpers (Django): `dissolve_singleton_threads`, `reconcile_story_threads`, `requeue_articles`.

See also [infrastructure/README.md](../../infrastructure/README.md).
