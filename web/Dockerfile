# Container image for AWS Lambda (Mangum) — build context: repo root
FROM public.ecr.aws/lambda/python:3.12 AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /build
COPY packages/n2s_api /build/packages/n2s_api
COPY web/pyproject.toml web/uv.lock /build/web/
WORKDIR /build/web
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

ENV PYTHONPATH=/var/task

CMD ["config.lambda_handler.handler"]
