# infra/

Docker infrastructure for self-hosted Dataing deployment.

## Quick Start

```bash
# 1. Configure environment
cp .env.example .env
# Edit .env: add ANTHROPIC_API_KEY and generate DATADR_ENCRYPTION_KEY

# 2. Start all services
docker compose up -d

# 3. Verify health
bash infra/smoke-test.sh
```

## Access

- Frontend: http://localhost:3000
- API: http://localhost:8000
- Temporal UI: http://localhost:8233

## Commands

```bash
docker compose up -d      # Start stack
docker compose down       # Stop (keep data)
docker compose down -v    # Stop + delete data
docker compose logs -f    # View logs
```

## Files

| File | Purpose |
|------|---------|
| `Dockerfile.backend` | API + worker image |
| `Dockerfile.frontend` | nginx + React image |
| `nginx.conf` | Frontend proxy config |
| `init-temporal-db.sh` | Temporal DB setup |
| `smoke-test.sh` | Health verification |
| `check-env.sh` | Env validation |
