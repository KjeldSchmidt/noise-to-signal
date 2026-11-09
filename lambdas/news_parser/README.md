# news_parser

SQS-triggered worker: receives `FeedItem` messages, enriches them, upserts `Article` via Django `POST /api/internal/articles/`.

## Enrichment

1. Normalize `title` / `summary` to plain text (unescape HTML, strip tags, collapse whitespace).
2. Embed `title + summary` with **Cohere Embed Multilingual v3** on Bedrock (`cohere.embed-multilingual-v3`, `input_type=clustering`).
3. Structured place + theme extract via Bedrock Converse (`amazon.nova-micro-v1:0` by default): `geo_scope`, place query, allowlisted `theme_slugs`.
4. If not global and confidence is high enough → `POST /api/internal/geocode/search/` (Nominatim hierarchy: country / admin1 / locality + coords). Geo failures fall back to `geo_level=global` (article + embedding still upsert).
5. Upsert article + embedding + place + themes; the web API assigns **near-dup** / **story thread** links and validates theme slugs against the curated `Theme` catalog.

No article-body scraping in this phase (RSS text only). Embedding / hard failures report SQS `batchItemFailures` so the message retries; geo/theme extract soft-fails.

## Prerequisites

- Bedrock model access for `cohere.embed-multilingual-v3` and the extract model (default Nova Micro) in the worker region (or set `BEDROCK_REGION`).
- IAM invoke/converse on those models (Terraform: `invoke_bedrock = true` on the worker).
- Postgres with `pgvector` (`CREATE EXTENSION vector`) on the web DB.
- Migrated theme seed (`0005_article_place_themes`).

## Env

| Variable | Purpose |
|----------|---------|
| `WEB_API_BASE_URL` | Public web origin |
| `INTERNAL_API_TOKEN` | Bearer for `/api/internal/*` |
| `BEDROCK_REGION` | Optional Bedrock region override |
| `BEDROCK_EXTRACT_MODEL_ID` | Optional; default `amazon.nova-micro-v1:0` |

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
