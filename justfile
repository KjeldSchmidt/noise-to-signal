# noise-to-signal — root quality + repo setup
set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

default:
    @just --list

setup-repo:
    git config core.hooksPath .githooks

# Format terraform + all Python projects
fmt:
    just --justfile infrastructure/justfile --working-directory infrastructure fmt
    just --justfile web/justfile --working-directory web fmt
    just --justfile lambdas/feed_consumer/justfile --working-directory lambdas/feed_consumer fmt
    just --justfile lambdas/news_parser/justfile --working-directory lambdas/news_parser fmt
    just --justfile lambdas/news_chat/justfile --working-directory lambdas/news_chat fmt
    just --justfile lambdas/brief_builder/justfile --working-directory lambdas/brief_builder fmt
    just --justfile lambdas/story_summarizer/justfile --working-directory lambdas/story_summarizer fmt
    just --justfile packages/n2s_api/justfile --working-directory packages/n2s_api fmt
    just --justfile packages/n2s_web_client/justfile --working-directory packages/n2s_web_client fmt
    just --justfile packages/n2s_preferences/justfile --working-directory packages/n2s_preferences fmt

fmt-check:
    just --justfile infrastructure/justfile --working-directory infrastructure fmt-check
    just --justfile web/justfile --working-directory web fmt-check
    just --justfile lambdas/feed_consumer/justfile --working-directory lambdas/feed_consumer fmt-check
    just --justfile lambdas/news_parser/justfile --working-directory lambdas/news_parser fmt-check
    just --justfile lambdas/news_chat/justfile --working-directory lambdas/news_chat fmt-check
    just --justfile lambdas/brief_builder/justfile --working-directory lambdas/brief_builder fmt-check
    just --justfile lambdas/story_summarizer/justfile --working-directory lambdas/story_summarizer fmt-check
    just --justfile packages/n2s_api/justfile --working-directory packages/n2s_api fmt-check
    just --justfile packages/n2s_web_client/justfile --working-directory packages/n2s_web_client fmt-check
    just --justfile packages/n2s_preferences/justfile --working-directory packages/n2s_preferences fmt-check

# Auto-fix lint issues (manual / agent; not CI)
lint:
    just --justfile web/justfile --working-directory web lint
    just --justfile lambdas/feed_consumer/justfile --working-directory lambdas/feed_consumer lint
    just --justfile lambdas/news_parser/justfile --working-directory lambdas/news_parser lint
    just --justfile lambdas/news_chat/justfile --working-directory lambdas/news_chat lint
    just --justfile lambdas/brief_builder/justfile --working-directory lambdas/brief_builder lint
    just --justfile lambdas/story_summarizer/justfile --working-directory lambdas/story_summarizer lint
    just --justfile packages/n2s_api/justfile --working-directory packages/n2s_api lint
    just --justfile packages/n2s_web_client/justfile --working-directory packages/n2s_web_client lint
    just --justfile packages/n2s_preferences/justfile --working-directory packages/n2s_preferences lint

lint-check:
    just --justfile web/justfile --working-directory web lint-check
    just --justfile lambdas/feed_consumer/justfile --working-directory lambdas/feed_consumer lint-check
    just --justfile lambdas/news_parser/justfile --working-directory lambdas/news_parser lint-check
    just --justfile lambdas/news_chat/justfile --working-directory lambdas/news_chat lint-check
    just --justfile lambdas/brief_builder/justfile --working-directory lambdas/brief_builder lint-check
    just --justfile lambdas/story_summarizer/justfile --working-directory lambdas/story_summarizer lint-check
    just --justfile packages/n2s_api/justfile --working-directory packages/n2s_api lint-check
    just --justfile packages/n2s_web_client/justfile --working-directory packages/n2s_web_client lint-check
    just --justfile packages/n2s_preferences/justfile --working-directory packages/n2s_preferences lint-check

typecheck:
    just --justfile web/justfile --working-directory web typecheck
    just --justfile lambdas/feed_consumer/justfile --working-directory lambdas/feed_consumer typecheck
    just --justfile lambdas/news_parser/justfile --working-directory lambdas/news_parser typecheck
    just --justfile lambdas/news_chat/justfile --working-directory lambdas/news_chat typecheck
    just --justfile lambdas/brief_builder/justfile --working-directory lambdas/brief_builder typecheck
    just --justfile lambdas/story_summarizer/justfile --working-directory lambdas/story_summarizer typecheck
    just --justfile packages/n2s_api/justfile --working-directory packages/n2s_api typecheck
    just --justfile packages/n2s_web_client/justfile --working-directory packages/n2s_web_client typecheck
    just --justfile packages/n2s_preferences/justfile --working-directory packages/n2s_preferences typecheck

test:
    just --justfile web/justfile --working-directory web test
    just --justfile lambdas/feed_consumer/justfile --working-directory lambdas/feed_consumer test
    just --justfile lambdas/news_parser/justfile --working-directory lambdas/news_parser test
    just --justfile lambdas/news_chat/justfile --working-directory lambdas/news_chat test
    just --justfile lambdas/brief_builder/justfile --working-directory lambdas/brief_builder test
    just --justfile lambdas/story_summarizer/justfile --working-directory lambdas/story_summarizer test
    just --justfile packages/n2s_api/justfile --working-directory packages/n2s_api test
    just --justfile packages/n2s_web_client/justfile --working-directory packages/n2s_web_client test
    just --justfile packages/n2s_preferences/justfile --working-directory packages/n2s_preferences test

# Full quality gate (CI / PR / local on demand)
check: fmt-check lint-check typecheck test
