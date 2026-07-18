# ============================================================================
# Builder stage: compile wheels so the runtime image needs no toolchain
# ============================================================================
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# requirements.lock rather than requirements.txt: it pins every transitive
# dependency with a sha256, so --require-hashes makes the build reject any
# package whose content does not match what was locked. requirements.txt pins
# only direct dependencies by version, which a compromised or re-uploaded
# transitive package can still slip past.
# Regenerate with:
#   pip-compile --generate-hashes --output-file=requirements.lock requirements.txt
COPY requirements.lock .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip wheel --no-cache-dir --require-hashes --wheel-dir /build/wheels \
        --requirement requirements.lock

# ============================================================================
# Runtime stage
# ============================================================================
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# libpq5 for asyncpg/psycopg at runtime, curl only for the healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 devops && \
    mkdir -p /data && \
    chown -R devops:devops /app /data

# Install dependencies before copying source so code changes don't bust this layer
COPY requirements.lock /app/requirements.lock
RUN --mount=type=bind,from=builder,source=/build/wheels,target=/wheels \
    pip install --no-cache-dir --no-index --find-links /wheels \
        --requirement /app/requirements.lock

# Copy application
COPY --chown=devops:devops . /app

# Switch to non-root user
USER devops

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# WEB_CONCURRENCY controls uvicorn worker count (default 1)
CMD ["sh", "-c", "uvicorn ai_devops_assistant.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-1}"]
