# noise-to-signal (web)

Django frontend for the personal news aggregator MVP. Placeholder ranking and follow-up questions — the LangGraph core in `../runner` is intentionally untouched.

Auth is **Google-only** (django-allauth) for humans. Django still has a `User` row per person; passwords are not used for end users.

Machine callers (Lambdas) use a shared bearer token (`INTERNAL_API_TOKEN`) against `/api/internal/*`. On AWS the token is generated in Terraform and stored in the app Secrets Manager secret; locally set it in `.env`.

Request/response shapes live in `packages/n2s_api` (`n2s-api`). Worker Lambdas talk to Django through `packages/n2s_web_client` (`n2s-web-client`, depends on `n2s-api`). Both are uv path deps (no workspace — each app keeps its own lockfile/venv).

## Google OAuth setup (where to put credentials)

1. In [Google Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials), create an **OAuth 2.0 Client ID** of type **Web application**.
2. Authorized JavaScript origins:
   - Local: `http://127.0.0.1:8000`
   - Dev: `https://beta.noise-to-signal.fyi`
3. Authorized redirect URIs (exact):
   - Local: `http://127.0.0.1:8000/accounts/google/login/callback/`
   - Dev: `https://beta.noise-to-signal.fyi/accounts/google/login/callback/`
4. Put the client ID and secret in **`web/.env`** (local) or Secrets Manager (AWS):

```
GOOGLE_CLIENT_ID=....apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=....
```

Do not commit `.env`. A template is in [`.env.example`](.env.example).

**Important:** after editing `.env`, fully stop and start `runserver` (Ctrl+C, then start again). Django’s auto-reloader does **not** reload environment variables.

Also set `SITE_DOMAIN` to match the host (no scheme):

```
SITE_DOMAIN=127.0.0.1:8000
# AWS:
SITE_DOMAIN=beta.noise-to-signal.fyi
```

## Local development

From `web/`, `just` lists recipes:

```bash
cd web
cp .env.example .env   # then fill GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET
just sync
just setup             # migrate + seed
just run
```

Open http://127.0.0.1:8000 → **Continue with Google**.

Without `DATABASE_URL`, SQLite (`db.sqlite3`) is used. To use the shared AWS RDS lab DB:

```
DATABASE_URL=postgresql://tckadmin:…@tck-labs-shared.cjmwyu84sg6w.eu-central-1.rds.amazonaws.com:5432/noise_to_signal_dev?sslmode=require
DATABASE_SSL=true
```

Article embeddings need **Postgres + pgvector** (`CREATE EXTENSION vector`). Local SQLite can run the schema for smoke tests but production similarity/thread assignment targets RDS.

Articles also store hierarchical place fields + curated **Theme** M2M (seeded in migration `0005`). Workers call `GET /api/internal/themes/` and `POST /api/internal/geocode/search/`; LOI settings persist the same country/admin1/locality path for containment matching (`news.services.places.places_match`).

## Deploy on AWS (Lambda container + shared RDS)

See [`../infrastructure/README.md`](../infrastructure/README.md).

### Caveats

- Cold starts are expected; idle compute cost is ~$0.
