# Build-time Python version argument
ARG PYTHONIMAGEVERSION=3.13-slim
FROM python:${PYTHONIMAGEVERSION}

# Prevent Python from writing pyc files and using stdout buffering
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install dependencies: Chrome
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl unzip wget gnupg docker.io chromium chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Install kubectl
RUN curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" \
    && install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl \
    && rm kubectl

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements/ /app/requirements/
RUN pip install --no-cache-dir -r /app/requirements/prod.txt

# Copy source code
COPY . .

# Expose MCP server port
EXPOSE 8000

# Default command
CMD ["python", "server.py"]
