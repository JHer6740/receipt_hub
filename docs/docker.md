# Receipts Hub — Docker & Containerization Guide

**Version**: 1.0  
**Date**: August 2026  
**Audience**: DevOps, deployment engineers, local development

---

## Overview

Receipts Hub is containerized using Docker for both development and production deployment. The MVP runs on a private LAN using a single `docker-compose` stack; the hosted phase adds PostgreSQL, Redis, background workers, and orchestration via Kubernetes or Docker Swarm.

### Key Design Decisions

1. **Multi-stage build**: Reduces final image size by separating build and runtime environments
2. **Non-root user**: Runs as unprivileged `appuser` (UID 1000) for security
3. **Volume mounting**: Persistent data (SQLite, receipt images) stored in `/app/data`
4. **Health checks**: Built-in Docker health check to monitor service readiness
5. **No secrets in image**: Configuration via environment variables (set at runtime)

---

## Prerequisites

### For Local Development

- Docker Desktop 4.10+ (includes Docker Compose v2)
- Git
- 2 GB free disk space (for images and data)
- Port 8000 available

### For Production (MVP — Private LAN)

- Docker Server 20.10+ on Windows/Linux/Mac
- Docker Compose v2+
- Persistent storage (mounted volume or bind mount)
- Network connectivity to Flutter clients on same LAN

### For Hosted Phase (Later)

- Kubernetes 1.22+, or Docker Swarm
- PostgreSQL 15+
- Redis 7+
- Private container registry (ECR, GCR, Docker Hub private)
- CI/CD platform (GitHub Actions, GitLab CI, Jenkins)

---

## 1. MVP Deployment — Single Container Stack

### 1.1 File Structure

```
receipts-hub/
├── Dockerfile                          # Backend image definition
├── docker-compose.yml                  # MVP stack orchestration
├── .dockerignore                       # Build context exclusions
├── receipts - grocery home/
│   ├── Dockerfile                      # (Alternative: can use root Dockerfile)
│   ├── pyproject.toml
│   ├── poetry.lock  (or requirements.txt)
│   ├── grocery_home/
│   │   ├── app.py
│   │   ├── models.py
│   │   ├── config.py
│   │   └── ...
│   └── data/                           # Persisted volume
│       ├── household.db                # SQLite
│       └── receipts/
└── ...
```

### 1.2 Build the Image

**Option A: Build locally for development**

```bash
# From workspace root
cd receipts\ -\ grocery\ home
docker build -t receipts-hub-backend:latest .
```

**Option B: Use docker-compose (automatic build)**

```bash
# From workspace root
docker-compose build fastapi
```

### 1.3 Run the Stack

#### First-Time Setup

If no household is configured, run setup:

```bash
# Interactive setup (one-time)
docker-compose run --rm fastapi python -m grocery_home.cli setup
```

This will prompt for:
- Household name (e.g., "Smiths")
- Shared PIN (not echoed)
- Database initialization
- Session secret generation

The database is created in the persisted volume at `./receipts - grocery home/data/household.db`.

#### Start the Service

```bash
# Start in background
docker-compose up -d

# Or foreground (useful for debugging)
docker-compose up
```

**Output:**
```
[+] Running 1/1
 ⠿ Container receipts-hub-backend  Started
```

### 1.4 Verify the Stack

```bash
# Check service status
docker-compose ps

# Expected output:
# NAME                           STATUS
# receipts-hub-backend           Up (healthy)

# View logs
docker-compose logs -f fastapi

# Test health endpoint
curl http://localhost:8000/health

# Expected response:
# {"status": "ok", "timestamp": "2026-08-16T..."}
```

### 1.5 Access the App

| Route | Purpose |
|-------|---------|
| `http://localhost:8000` | Home (Jinja-rendered web UI) |
| `http://localhost:8000/docs` | Swagger UI (interactive API explorer) |
| `http://localhost:8000/redoc` | ReDoc (alternative API docs) |
| `http://localhost:8000/api/v1/bootstrap` | JSON API (requires auth token) |
| `http://localhost:8000/health` | Health check |

### 1.6 Stop & Clean Up

```bash
# Stop services (data persists)
docker-compose down

# Remove services AND data volume
docker-compose down -v

# View data directory
ls -la ./receipts\ -\ grocery\ home/data/
```

---

## 2. Development Workflow

### 2.1 Hot Reload (Not Recommended for Fastapi in This Setup)

FastAPI with Uvicorn supports `--reload`, but it's better to use the native development command for Python:

```bash
# Stop container
docker-compose down

# Run locally for development
cd receipts\ -\ grocery\ home
python -m uvicorn grocery_home.app:app --reload --host 0.0.0.0 --port 8000
```

### 2.2 Debug with Docker

To run the container in debug mode with interactive shell:

```bash
docker-compose run --rm -it fastapi bash

# Inside container:
$ python -m pytest tests/ -v
$ python -m uvicorn grocery_home.app:app --reload
```

### 2.3 Override Compose for Development

Create a `docker-compose.override.yml` (not tracked in git):

```yaml
version: '3.9'
services:
  fastapi:
    build:
      context: ./receipts\ -\ grocery\ home
      dockerfile: Dockerfile
    volumes:
      # Mount source for live edits
      - ./receipts\ -\ grocery\ home:/app
    environment:
      # Enable debug logging
      GROCERY_HOME_LOG_LEVEL: DEBUG
    command: python -m uvicorn grocery_home.app:app --reload --host 0.0.0.0 --port 8000
```

Then:
```bash
docker-compose up  # Automatically loads override.yml
```

---

## 3. LAN Deployment (MVP)

### 3.1 Network Setup

Assuming a private home network:
- Host machine: 192.168.1.100 (example)
- Flutter clients: 192.168.1.101–110

**Docker on Windows:**
- Container listens on `0.0.0.0:8000` inside the container
- Exposed to host on `localhost:8000` and `<host_ip>:8000`

**Docker on Linux:**
- Bridge network allows direct access from other machines on the LAN

### 3.2 Configure Flutter Client

In Flutter app settings:

```
Server URL: http://192.168.1.100:8000
PIN: [entered at setup]
```

The Flutter app will:
1. Resolve `192.168.1.100` on the LAN (no DNS needed)
2. Make HTTP requests to `/api/v1/auth/pin` (cleartext OK on trusted LAN)
3. Store session token in secure storage

### 3.3 Windows Firewall (If Needed)

If the host running Docker is behind Windows Firewall:

```powershell
# Allow inbound traffic on port 8000
New-NetFirewallRule -DisplayName "Receipts Hub" `
  -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000
```

Or via GUI:
- Windows Defender Firewall → Inbound Rules → New Rule
- Port 8000, TCP, Allow

### 3.4 Keep-Alive & Auto-Restart

Ensure Docker starts on boot and restarts service on crash:

**Windows (via Docker Desktop):**
- Settings → General → "Start Docker Desktop when you log in"

**Linux (systemd):**
```bash
sudo systemctl enable docker
sudo systemctl start docker
```

**docker-compose auto-restart:**
```bash
# Already enabled in docker-compose.yml
# restart: unless-stopped
```

---

## 4. Production-Ready Tweaks (Hosted Phase)

### 4.1 Image Optimization

**Reduce size:**
```dockerfile
# Use Alpine instead of slim (if compatible)
FROM python:3.12-alpine

# Skip documentation
RUN pip install --no-cache-dir --no-docs ...
```

**Current size:** ~400 MB (slim + OCR deps)
**Alpine size:** ~250 MB (if OCR compatible)

### 4.2 Security Hardening

```dockerfile
# Read-only root filesystem (host must handle init)
RUN chmod -R 755 /app

# Drop capabilities
RUN setcap -r /bin/ping

# Scan for vulnerabilities
RUN pip install safety && safety check --json
```

### 4.3 Logging & Monitoring

**Structured JSON logging:**

```python
# In grocery_home/app.py
import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info(json.dumps({
    "event": "receipt_confirmed",
    "household_id": household.id,
    "receipt_id": receipt.id,
    "timestamp": datetime.now(UTC).isoformat()
}))
```

**Docker logs:**
```bash
docker logs receipts-hub-backend --follow

# Aggregate with ELK / Datadog / CloudWatch
docker logs receipts-hub-backend --format '{{.FullID}} {{.CreatedAt}} {{.Message}}'
```

### 4.4 Multi-Service Stack (PostgreSQL, Redis)

```yaml
version: '3.9'
services:
  fastapi:
    # ... (same as above)
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql://user:pass@postgres:5432/receipts_hub
      REDIS_URL: redis://redis:6379/0

  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: receipts_hub
      POSTGRES_PASSWORD: ${DB_PASSWORD}  # From .env
      POSTGRES_DB: receipts_hub
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U receipts_hub"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
  redis_data:
```

---

## 5. CI/CD Integration (GitHub Actions Example)

### 5.1 Automated Build & Push

Create `.github/workflows/docker-build.yml`:

```yaml
name: Build & Push Docker Image

on:
  push:
    branches:
      - main
      - develop
    paths:
      - 'receipts - grocery home/**'
      - 'Dockerfile'
      - 'docker-compose.yml'
      - '.github/workflows/docker-build.yml'

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2

      - name: Login to Container Registry
        uses: docker/login-action@v2
        with:
          registry: docker.io
          username: ${{ secrets.DOCKER_USERNAME }}
          password: ${{ secrets.DOCKER_PASSWORD }}

      - name: Build and Push
        uses: docker/build-push-action@v4
        with:
          context: ./receipts\ -\ grocery\ home
          file: ./receipts\ -\ grocery\ home/Dockerfile
          push: true
          tags: |
            myregistry/receipts-hub-backend:latest
            myregistry/receipts-hub-backend:${{ github.sha }}
```

### 5.2 Automated Testing in CI

```yaml
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15-alpine
        env:
          POSTGRES_DB: test_db
          POSTGRES_PASSWORD: test
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
        with:
          python-version: '3.12'
      - run: pip install -e ".[dev,ocr]"
      - run: pytest tests/ -v --cov=grocery_home --cov-report=xml
      - run: curl --output-dir coverage codecov.io/bash
```

---

## 6. Troubleshooting

### 6.1 Container Won't Start

```bash
# Check logs
docker-compose logs fastapi

# Common issues:
# - Port 8000 already in use:
#   docker ps
#   Kill conflicting container or use different port in compose

# - Data volume permission denied:
#   sudo chmod -R 777 ./receipts\ -\ grocery\ home/data

# - Database locked (SQLite):
#   rm ./receipts\ -\ grocery\ home/data/household.db-wal
#   rm ./receipts\ -\ grocery\ home/data/household.db-shm
#   docker-compose down -v
#   docker-compose up
```

### 6.2 Health Check Failing

```bash
# Inspect container
docker-compose exec fastapi sh

# Inside container:
$ curl http://localhost:8000/health
$ python -m uvicorn grocery_home.app:app --reload &
$ tail -f /var/log/app.log
```

### 6.3 Slow Performance

```bash
# Check resource usage
docker stats receipts-hub-backend

# If memory high:
docker-compose down
docker system prune  # Remove dangling images/volumes
docker-compose up

# Profile OCR:
docker-compose exec fastapi python -m cProfile -s cumulative -o profile.stats tests/test_ocr.py
```

### 6.4 Database Corruption

```bash
# Backup current data
cp -r ./receipts\ -\ grocery\ home/data ./receipts\ -\ grocery\ home/data.backup

# Reset and reinitialize
docker-compose down -v
docker-compose run --rm fastapi python -m grocery_home.cli setup
docker-compose up
```

---

## 7. Environment Variables Reference

| Variable | Default | Purpose |
|----------|---------|---------|
| `GROCERY_HOME_DATA_DIR` | `/app/data` | Path to SQLite, receipts, images |
| `GROCERY_HOME_HOST` | `0.0.0.0` | Bind address |
| `GROCERY_HOME_PORT` | `8000` | Bind port |
| `GROCERY_HOME_LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `GROCERY_HOME_HOUSEHOLD_PIN` | (none) | Initial PIN (set at first boot) |
| `DATABASE_URL` | `sqlite:///./data/household.db` | DB connection (for hosted: `postgresql://...`) |
| `REDIS_URL` | (none) | Redis cache URL (hosted phase only) |

**Set via `.env` file:**
```bash
GROCERY_HOME_LOG_LEVEL=DEBUG
```

**Or inline:**
```bash
docker-compose run -e GROCERY_HOME_LOG_LEVEL=DEBUG fastapi
```

---

## 8. Backup & Recovery

### 8.1 Backup Data

```bash
# While container is running
docker-compose exec fastapi ls -la /app/data/

# Or copy to host
docker cp receipts-hub-backend:/app/data ./data-backup-$(date +%s)

# Verify
ls -la ./data-backup-*
```

### 8.2 Restore Data

```bash
# Stop container
docker-compose down

# Restore from backup
rm -rf ./receipts\ -\ grocery\ home/data/*
cp -r ./data-backup-<timestamp>/* ./receipts\ -\ grocery\ home/data/

# Restart
docker-compose up
```

---

## 9. Quick Reference Commands

```bash
# Build
docker-compose build

# Start
docker-compose up -d

# Stop
docker-compose down

# Logs
docker-compose logs -f fastapi

# Status
docker-compose ps

# Shell
docker-compose exec fastapi sh

# Run one-off command
docker-compose run --rm fastapi python -m pytest tests/

# Full reset
docker-compose down -v && docker system prune -a
```

---

## 10. Next Steps (Hosted Phase)

1. **PostgreSQL migration**: Update `DATABASE_URL` and run Alembic migrations
2. **Redis caching**: Add Redis service and update analytics cache strategy
3. **Background workers**: Add Celery/RQ service for OCR, price refresh
4. **Load balancer**: Add Nginx or HAProxy in front of multiple app instances
5. **Kubernetes**: Migrate to K8s with Helm charts for auto-scaling, zero-downtime deployments
6. **Private registry**: Push images to ECR/GCR instead of Docker Hub
7. **Monitoring**: Add Prometheus + Grafana, distributed tracing (Jaeger)

---

## References

- [Docker documentation](https://docs.docker.com/)
- [Docker Compose specification](https://docs.docker.com/compose/compose-file/)
- [FastAPI deployment guide](https://fastapi.tiangolo.com/deployment/)
- [REQUIREMENTS.md](../REQUIREMENTS.md) — Product & technical spec
- [API specification](./api.md) — `/api/v1` endpoint contract
