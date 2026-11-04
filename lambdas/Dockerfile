# Generic worker Lambda image — build context: repo root
#   docker build -f lambdas/Dockerfile --build-arg LAMBDA_NAME=feed_consumer .
ARG LAMBDA_NAME

FROM public.ecr.aws/lambda/python:3.12 AS builder

ARG LAMBDA_NAME
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /build
COPY packages/n2s_api /build/packages/n2s_api
COPY packages/n2s_web_client /build/packages/n2s_web_client
COPY lambdas/${LAMBDA_NAME}/pyproject.toml lambdas/${LAMBDA_NAME}/uv.lock /build/lambdas/${LAMBDA_NAME}/
WORKDIR /build/lambdas/${LAMBDA_NAME}
RUN uv sync --frozen --no-dev --no-install-project --no-editable

COPY lambdas/${LAMBDA_NAME}/ /build/lambdas/${LAMBDA_NAME}/
RUN uv sync --frozen --no-dev --no-install-project --no-editable

# --- runtime ---
FROM public.ecr.aws/lambda/python:3.12

ARG LAMBDA_NAME
COPY --from=builder /build/lambdas/${LAMBDA_NAME}/.venv/lib/python3.12/site-packages /var/lang/lib/python3.12/site-packages
COPY --from=builder /build/lambdas/${LAMBDA_NAME}/ /var/task/

ENV PYTHONPATH=/var/task

CMD ["main.handler"]
