# noise-to-signal

A personal news aggregator: subscribe to RSS feeds, build a personalized daily brief against your taste, give relevance feedback, and ask short follow-up questions. The **web UI** is Django; enrichment, brief personalization, and chat run as **LangGraph workers on AWS Lambda** with **Amazon Bedrock** (EU).

## Repository layout

| Path | Role |
|------|------|
| [`web/`](web/) | Django app (feeds, stories, briefs, settings, internal API) |
| [`lambdas/`](lambdas/) | Workers: feed consumer, news parser, brief builder, news chat, story summarizer |
| [`packages/`](packages/) | Shared contracts (`n2s_api`), web client, AgentCore preference client |
| [`infrastructure/`](infrastructure/) | Lambda + Function URL + ECR; DBs on shared tck-labs RDS |

## Architecture overview

```
RSS feeds ──► feed_consumer ──► news_parser (enrich)
                                      │
                                      ▼
                              Postgres (articles / threads)
                                      │
              ┌───────────────────────┼───────────────────────┐
              ▼                       ▼                       ▼
         Stories feed          brief_builder            news_chat
         (impact×decay)     (AgentCore prefs +          (grounded Q&A;
                             theme/LOI ranking →         may save prefs)
                             UserBrief)
```

**Preference memory** uses **Amazon Bedrock AgentCore Memory** (`USER_PREFERENCE` strategy) in an EU region — not mem0. Theme more/less leanings live in Postgres and fold into brief candidate scores with locations of interest.

## Product / ops knobs

Defaults and env overrides for brief freshness, chat limits, payload caps, and model IDs live in [`packages/n2s_api/n2s_api/tunables.py`](packages/n2s_api/n2s_api/tunables.py). Override with `N2S_*` (product) or `BEDROCK_*` (models); code defaults apply when unset.

| Knob | Where to change |
|------|-----------------|
| Brief TTL, interim/candidate/max items, chat rate limits, payload caps, tool rounds | `tunables.py` / `N2S_*` env |
| Model IDs | `tunables.py` defaults; deploy overrides via `BEDROCK_*` in [`infrastructure/modules/workers/main.tf`](infrastructure/modules/workers/main.tf) |
| RSS feed poll cadence | `schedule_expression` in `infrastructure/env/{dev,prod}/app/main.tf` (not the same as brief TTL) |

`BRIEF_TTL` is how long a ready brief stays fresh; EventBridge schedules only control how often `feed_consumer` polls RSS.

## Web app

- Google sign-in (django-allauth; no end-user passwords)
- Curated feed catalog, custom RSS, stories feed, daily brief
- Theme leanings, locations of interest, free-form prefs via brief chat
- Relevance feedback (relevant / not / skip)

See [`web/README.md`](web/README.md) for local run and Google OAuth.

```bash
cd web
cp .env.example .env   # add GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET
just sync
just setup
just run
```

## Hosting (AWS)

- **Compute:** Lambda + CloudFront (scale to zero) — see [`infrastructure/README.md`](infrastructure/README.md)
- **Database:** dedicated Postgres DBs `noise_to_signal_dev` / `noise_to_signal_prod` on the shared [tck-labs-base](../tck-labs-base) RDS host
