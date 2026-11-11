# noise-to-signal infrastructure (AWS)

Django on **Lambda (container image) → Function URL → CloudFront**, image in **shared ECR**, data on shared [tck-labs-base](../../tck-labs-base) RDS. Worker Lambdas (e.g. `feed_consumer`) share the same ECR repo with prefixed tags and call the web internal API on a schedule.

## Stacks

| Stack | Path | State key | Contains |
|-------|------|-----------|----------|
| **shared** | [`env/shared`](env/shared) | `noise-to-signal.shared.tfstate` | ECR + Route 53 (`noise-to-signal.fyi`) + ACM wildcard |
| **app (dev)** | [`env/dev/app`](env/dev/app) | `noise-to-signal.dev.app.tfstate` | Web Lambda, workers, Function URL, CloudFront, `beta.noise-to-signal.fyi` |
| **app (prod)** | [`env/prod/app`](env/prod/app) | `noise-to-signal.prod.app.tfstate` | Same shape → apex `noise-to-signal.fyi` |

Environments share ECR + DNS; distinguish releases with **image tags**.

| Env | Public URL |
|-----|------------|
| Dev | **https://beta.noise-to-signal.fyi/** |
| Prod | **https://noise-to-signal.fyi/** |

Deploy order: **shared → push web + worker images → app (dev) → app (prod)** (prod reuses the same image tag).

## Image tags (one ECR: `noise-to-signal`)

| Image | Tags |
|-------|------|
| Web (Django) | `<tag>`, `latest` |
| Worker `feed_consumer` | `feed_consumer-<tag>`, `feed_consumer-latest` |

Build workers with the generic [`../lambdas/Dockerfile`](../lambdas/Dockerfile) (`ARG LAMBDA_NAME`). Recipes: `just push-lambda <name> <tag>`, `just push-lambdas <tag>` (every `lambdas/*/pyproject.toml`).

## Worker Lambdas

- Module: [`modules/workers`](modules/workers), wired from each `env/<env>/app`.
- **`feed_consumer`** — EventBridge schedule; `list_feeds` → parse RSS → chunked `POST /api/internal/feed-items/`.
- **`news_parser`** — SQS (`<project>-<env>-feed-items`); LangGraph enrich (`normalize` → `embed` ∥ `extract_place` → `upsert`) → `POST /api/internal/articles/` (thread assignment on the web).
- Env: `WEB_API_BASE_URL`, `INTERNAL_API_TOKEN` (+ `BEDROCK_REGION` / `BEDROCK_EXTRACT_MODEL_ID` when `invoke_bedrock`; + `LANGSMITH_*` when `langsmith_agent_id` is set); web also gets `FEED_ITEMS_QUEUE_URL`.
- Deployable workers = dirs under `lambdas/` with `pyproject.toml`.

## pgvector + Bedrock (embeddings + place/themes)

On each app database (once per env), as a role that can create extensions:

```sql
\c noise_to_signal_dev
CREATE EXTENSION IF NOT EXISTS vector;
\c noise_to_signal_prod
CREATE EXTENSION IF NOT EXISTS vector;
```

Django migration `0004_article_embedding_storythread` also runs `CREATE EXTENSION IF NOT EXISTS vector` when the vendor is PostgreSQL (no-op on SQLite). Migration `0005_article_place_themes` adds hierarchical place fields, curated `Theme` rows, and article↔theme M2M.

Enable **Cohere Embed Multilingual v3** and the extract model (**EU Nova Micro inference profile** `eu.amazon.nova-micro-v1:0` by default — bare foundation-model IDs fail on-demand Converse) in Bedrock model access for the account/region used by `news_parser`. Embeddings use `input_type=clustering` on cleaned RSS `title + summary` (no article scrape yet). Place/theme extract is one Converse call with enum-constrained curated themes plus free-form `suggested_themes` (counted in `ThemeSuggestion` for promotion); Nominatim hierarchy via `POST /api/internal/geocode/search/` (fail soft → `global`).

Similarity lanes (applied in the web upsert path). Articles often have **no** story thread; threads emerge when pairs/clusters form:

| Lane | Cosine | Time | Role |
|------|--------|------|------|
| Near-dup | ≥ 0.92 | ±48h | Multi-source same-day collapse → shared thread |
| Open thread | ≥ 0.78 vs centroid | 45-day activity | Join evolving event (label stays stable) |
| Soft peer | ≥ 0.78 vs unthreaded peer | 45-day window | Create thread for both |

**SCALING HOTSPOT:** story assignment uses a global Postgres advisory lock (`pg_advisory_xact_lock`) to avoid missed pairs under concurrent `news_parser` upserts. Fine now; may serialize linking under heavy load — see `news.services.threading` and `rg "SCALING HOTSPOT"`.

Geo matching against user `LocationOfInterest` uses admin containment (`places_match`); city-level haversine (~50 km) only between locality peers — never against a country centroid.

## Cost model

- Scale to zero on compute (Lambda). Idle ≈ shared RDS + Secrets Manager (+ CloudFront when requested).
- Public URL is stable CloudFront `d….cloudfront.net` (Google OAuth). Raw `*.lambda-url.*` is origin-only.

## Isolation model

```sql
CREATE DATABASE noise_to_signal_dev;
CREATE DATABASE noise_to_signal_prod;
```

## Internal API token

Terraform generates `INTERNAL_API_TOKEN` into the per-env app secret (`noise-to-signal/<env>/app`) and injects it into the web Lambda and worker Lambdas. Workers call `https://<public-host>/api/internal/...` with `Authorization: Bearer <token>`.

## LangSmith (worker tracing)

Workers with `langsmith_agent_id` (e.g. `news_parser` → `news-parser`) get agent-based LangSmith tracing. The API key lives in Secrets Manager `noise-to-signal/<env>/langsmith` (JSON `LANGSMITH_API_KEY`), upserted from root `.env`:

```bash
cd infrastructure
APP_ENV=dev just upsert-langsmith
# APP_ENV=prod just upsert-langsmith
```

Terraform injects `LANGSMITH_API_KEY`, `LANGSMITH_TRACING`, `LANGSMITH_ENDPOINT`, `LANGSMITH_AGENT_ID`, and `LANGSMITH_AGENT_ENVIRONMENT` (`development` / `production`). Do not set `LANGSMITH_PROJECT` on those Lambdas. Create each agent once in the LangSmith UI before deploy.

## Prerequisites

- WSL + AWS SSO: `AWS_PROFILE=AdministratorAccess-465836752303`
- [`just`](https://github.com/casey/just), Docker, `psql`, Google OAuth client
- Shared RDS via tck-labs-base

```bash
cd infrastructure
export AWS_PROFILE=AdministratorAccess-465836752303
just
```

## Layout

| Path | Role |
|------|------|
| [`justfile`](justfile) | `apply-shared`, `push-image`, `push-lambdas`, `apply-app`, `deploy`, … |
| [`modules/ecr`](modules/ecr) | Shared ECR |
| [`modules/dns`](modules/dns) | Route 53 zone + ACM (us-east-1) |
| [`modules/web_app`](modules/web_app) | Per-env web compute + CloudFront alias |
| [`modules/workers`](modules/workers) | Per-env worker Lambdas + EventBridge |
| [`env/shared`](env/shared) | Shared stack root |
| [`env/dev/app`](env/dev/app) | Dev app → `beta.noise-to-signal.fyi` |
| [`env/prod/app`](env/prod/app) | Prod app → `noise-to-signal.fyi` |

## GitHub Actions

[`.github/workflows/deploy-infra.yml`](../.github/workflows/deploy-infra.yml) — OIDC. Job chain:

`deploy-shared` (fmt/lint + ECR/DNS/ACM) → `deploy-dev` → `deploy-prod`.

Dev/prod are the same reusable workflow ([`deploy-env.yml`](../.github/workflows/deploy-env.yml)): apply + migrate/seed + `GET /health` smoke. Dev also builds/pushes images; prod reuses the same SHA tags.

**Repo secret:** `AWS_ROLE_ARN` only.

### First prod apply prerequisites

1. `noise_to_signal_prod` DB exists (`just create-databases`).
2. Secrets Manager secret `noise-to-signal/prod/google-oauth` exists (`APP_ENV=prod just upsert-google-oauth`).
3. Secrets Manager secret `noise-to-signal/prod/langsmith` exists (`APP_ENV=prod just upsert-langsmith`) before workers apply with `langsmith_agent_id`.
4. Google OAuth client allows origin + redirect for `https://noise-to-signal.fyi` (callback `/accounts/google/login/callback/`).
5. LangSmith agent `news-parser` exists in the workspace.

## State / existing AWS resources

**No `moved` blocks** were added when splitting stacks. New state keys start empty, so the next apply will **try to create** resources. If `noise-to-signal-dev` ECR / old Lambda / etc. already exist from earlier deploys, either:

1. Delete/orphan the old resources and let Terraform create the new names (`noise-to-signal` ECR, etc.), or
2. `terraform import` into the new shared/app states.

Older state keys (`noise-to-signal.dev.tfstate`, `….dev.base.tfstate`) are unused by this layout.
