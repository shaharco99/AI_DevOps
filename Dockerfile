# Multi-stage build for AI DevOps Copilot

# ============================================================================
# Stage 1: Builder
# ============================================================================
FROM python:3.11-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Create wheels
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir --wheel --no-deps --requirement requirements.txt

# ============================================================================
# Stage 2: Runtime
# ============================================================================
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy wheels from builder
COPY --from=builder /build/*.whl /tmp/wheels/

# Create non-root user
RUN useradd -m -u 1000 copilot && \
    mkdir -p /data && \
    chown -R copilot:copilot /app /data

# Copy application
COPY --chown=copilot:copilot . /app

# Install wheels
RUN pip install --no-cache-dir --no-index --find-links=/tmp/wheels /tmp/wheels/* && \
    rm -rf /tmp/wheels/

# Switch to non-root user
USER copilot

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "ai_devops_copilot.main:app", "--host", "0.0.0.0", "--port", "8000"]
