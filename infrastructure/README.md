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
- **`news_parser`** — SQS (`<project>-<env>-feed-items`); enrich → `POST /api/internal/articles/`.
- Env: `WEB_API_BASE_URL`, `INTERNAL_API_TOKEN`; web also gets `FEED_ITEMS_QUEUE_URL`.
- Deployable workers = dirs under `lambdas/` with `pyproject.toml`.

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

`deploy-dev` → `smoke-dev` (`GET /health`) → `deploy-prod` (same image SHA, no rebuild) → `smoke-prod` (`GET /health`).

**Repo secret:** `AWS_ROLE_ARN` only.

### First prod apply prerequisites

1. `noise_to_signal_prod` DB exists (`just create-databases`).
2. Secrets Manager secret `noise-to-signal/prod/google-oauth` exists (`APP_ENV=prod just upsert-google-oauth`).
3. Google OAuth client allows origin + redirect for `https://noise-to-signal.fyi` (callback `/accounts/google/login/callback/`).

## State / existing AWS resources

**No `moved` blocks** were added when splitting stacks. New state keys start empty, so the next apply will **try to create** resources. If `noise-to-signal-dev` ECR / old Lambda / etc. already exist from earlier deploys, either:

1. Delete/orphan the old resources and let Terraform create the new names (`noise-to-signal` ECR, etc.), or
2. `terraform import` into the new shared/app states.

Older state keys (`noise-to-signal.dev.tfstate`, `….dev.base.tfstate`) are unused by this layout.
