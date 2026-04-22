# Runtime image for AI DevOps Assistant
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 devops && \
    mkdir -p /data && \
    chown -R devops:devops /app /data

# Copy application
COPY --chown=devops:devops . /app

# Install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir --requirement /app/requirements.txt

# Switch to non-root user
USER devops

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "ai_devops_assistant.main:app", "--host", "0.0.0.0", "--port", "8000"]
