# Container image for AWS Lambda (Mangum) — build context: repo root
FROM public.ecr.aws/lambda/python:3.12 AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /build
COPY packages/n2s_api /build/packages/n2s_api
COPY web/pyproject.toml web/uv.lock /build/web/
WORKDIR /build/web
# --no-editable so path deps (n2s-api) are copied into site-packages (not a /build path)
RUN uv sync --frozen --no-dev --no-install-project --no-editable

COPY web/ /build/web/
ENV SECRET_KEY=build-only \
    DJANGO_SETTINGS_MODULE=config.settings
RUN uv sync --frozen --no-dev --no-editable \
    && uv run python manage.py collectstatic --noinput

# --- runtime ---
FROM public.ecr.aws/lambda/python:3.12

COPY --from=builder /build/web/.venv/lib/python3.12/site-packages /var/lang/lib/python3.12/site-packages
COPY --from=builder /build/web /var/task

# Ensure Django finds the project on PYTHONPATH
ENV PYTHONPATH=/var/task

CMD ["config.lambda_handler.handler"]
