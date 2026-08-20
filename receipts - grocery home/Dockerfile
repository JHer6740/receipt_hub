# Multi-stage build for Receipts Hub FastAPI backend
# Stage 1: Builder
FROM python:3.12-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .

# Build wheels
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /build/wheels -e .[ocr]

# Stage 2: Runtime
FROM python:3.12-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

# Copy wheels from builder
COPY --from=builder /build/wheels /wheels

# Install Python dependencies
RUN pip install --no-cache /wheels/*

# Copy source code
COPY . .

# Create data directory for SQLite and receipt images
RUN mkdir -p /app/data /app/data/receipts

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    GROCERY_HOME_DATA_DIR=/app/data

# Non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app/data
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Run FastAPI with Uvicorn
CMD ["python", "-m", "uvicorn", "grocery_home.app:app", \
     "--host", "0.0.0.0", \
     "--port", "8000"]
