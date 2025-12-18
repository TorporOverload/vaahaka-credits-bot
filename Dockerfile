# syntax=docker/dockerfile:1

# Use an official Python base image; project requires Python >= 3.10
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Keep uv quiet and deterministic in CI/containers
    UV_NO_PROGRESS=1 \
    UV_LINK_MODE=copy \
    # Place the virtualenv inside the project directory
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    # Prefer the prebuilt virtualenv at runtime
    PATH=/app/.venv/bin:$PATH \
    # Default DB location inside the container (can be overridden)
    DB_PATH=/data/vaahaka_credits.db

WORKDIR /app

# System deps (ssl/certs, curl for uv installer)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv (Astral) into /usr/local/bin
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && ln -sf /root/.local/bin/uv /usr/local/bin/uv

# Copy dependency metadata first for better layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies (no dev deps) using the lockfile
RUN uv sync --frozen --no-dev

# Copy the application code
COPY . .

# Create and switch to a non-root user
RUN useradd -m -u 10001 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data

# Persisted runtime data (SQLite database lives here by default)
VOLUME ["/data"]

USER appuser

# Run the bot using the prebuilt virtualenv (avoid recreating venv / downloading Python at runtime)
CMD ["python", "main.py"]
