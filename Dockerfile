# Multi-stage build for optimal image size and security
FROM python:3.13-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

# Copy dependency files
WORKDIR /app
COPY pyproject.toml uv.lock* ./

# Install dependencies to /app/.venv
RUN uv venv /app/.venv && \
    uv pip install --no-cache -r pyproject.toml

# ========== Runtime Stage ==========
FROM python:3.13-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 -s /bin/bash complira && \
    mkdir -p /app && \
    chown -R complira:complira /app

# Copy virtual environment from builder
COPY --from=builder --chown=complira:complira /app/.venv /app/.venv

# Set working directory
WORKDIR /app

# Copy application code
COPY --chown=complira:complira src/ ./src/
COPY --chown=complira:complira scripts/ ./scripts/

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src:$PYTHONPATH"

# Switch to non-root user
USER complira

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
