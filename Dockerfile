# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.14
ARG UV_VERSION=0.13.7

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM python:${PYTHON_VERSION}-slim AS builder

WORKDIR /build

COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./

RUN uv venv /opt/venv \
    && uv export \
        --quiet \
        --only-group frontend \
        --no-emit-project \
        --locked \
        --output-file /tmp/requirements-frontend.txt \
    && uv pip install \
        --quiet \
        --python /opt/venv/bin/python \
        --no-cache \
        --requirements /tmp/requirements-frontend.txt

FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_FILE_WATCHER_TYPE=none \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_PORT=8501

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

RUN groupadd --gid 10001 app \
    && useradd \
        --uid 10001 \
        --gid app \
        --create-home \
        --no-log-init \
        app

ENV HOME=/home/app

COPY --chown=app:app frontend ./frontend
COPY --chown=app:app api/__init__.py ./api/__init__.py
COPY --chown=app:app api/models ./api/models

USER app

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-m", "frontend.healthcheck"]

CMD ["python", "-m", "streamlit", "run", "frontend/app.py"]
