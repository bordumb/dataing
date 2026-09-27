# Deployment

## Architecture

| Component | Platform | URL |
|-----------|----------|-----|
| Frontend | Vercel | `https://dataing.dev` |
| Backend | Railway | `https://dataing-production.up.railway.app` |
| Worker | Railway | Internal service |
| Database | Railway PostgreSQL | Internal networking |
| Redis | Railway Redis | Internal networking |

---

## Backend & Worker (Railway)

URL: https://railway.com/project/5b7c7807-517c-451b-9408-03c13ca2b2ca

### 1. Create Project

```bash
npm install -g @railway/cli
railway login
railway init
```

### 2. Add Services

Railway Dashboard → **+ New**:
- **Database** → **PostgreSQL**
- **Database** → **Redis**

### 3. Link Services

Backend service → **Variables** → **Add Variable**:

```
DATABASE_URL = ${{Postgres.DATABASE_URL}}
REDIS_URL = ${{Redis.REDIS_URL}}
```

### 4. Configure Worker

The worker runs in a separate service (or same image with different command).
Command: `python -m dataing.entrypoints.worker`

Env vars same as Backend (needs `DATABASE_URL` and `REDIS_URL`).

### 5. Run Database Migrations

The PostgreSQL database needs tables created. Run migrations from your local machine:

```bash
# Get DATABASE_URL from Railway: PostgreSQL service → Connect → Copy URL
export DATABASE_URL="postgresql://postgres:xxx@xxx.railway.app:5432/railway"  # pragma: allowlist secret

# Run migrations
./python-packages/dataing/scripts/migrate-prod.sh
```

This applies each SQL file in `python-packages/dataing/migrations/` once and records it in
`schema_migrations`, so re-running it only applies new migrations. Demo seed data is skipped
unless you set `INCLUDE_SEEDS=true`. Use that for demo deployments only: it creates the
`demo@dataing.io` login with a published password. Databases migrated by earlier versions of
this script already have that login.

### 5. Add Required Env Vars

| Variable | Value |
|----------|-------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |

### 6. Enable Public URL

**Settings** → **Networking** → **Generate Domain**

### 7. Deploy

Railway auto-deploys from GitHub on push to `main`.

Manual deploy:
```bash
railway up
```

### Logs

Dashboard → Service → **Deployments** → **View Logs**

---

## Frontend (Vercel)

### 1. Import Project

- Go to [vercel.com](https://vercel.com) → **Add New Project**
- Import GitHub repo
- Set **Root Directory**: `frontend`
- Framework: **Vite** (auto-detected)

### 2. Environment Variables

**Settings** → **Environment Variables**:

| Variable | Value |
|----------|-------|
| `VITE_API_URL` | `https://dataing-production.up.railway.app` |

**Important**: No trailing slash.

### 3. Deploy

Vercel auto-deploys on push to `main`.

Manual redeploy: **Deployments** → **...** → **Redeploy**

After changing env vars, redeploy with **"Use existing Build Cache" = OFF**.

---

## Verification

### Backend Health

```bash
curl https://dataing-production.up.railway.app/health
# {"status":"healthy"}
```

### Database Connection

Railway logs should show:
```
app_database_connected dsn=... attempt=1
```

---

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `HTTP 405` on login | Frontend calling Vercel not Railway | Set `VITE_API_URL` with `https://` prefix in Vercel, redeploy |
| `Connection refused` on startup | Postgres not ready | Retry logic handles this; check DB is provisioned |
| `Distribution not found: bond` | Deploying from wrong root | Deploy from repo root, not `dataing/` |
| TypeScript build errors | Missing generated files | Ensure `frontend/src/lib/api/generated/` is in git |
| "No tables" in Railway Postgres | Migrations not run | Run `./python-packages/dataing/scripts/migrate-prod.sh` |
| Demo login missing on a demo deployment | Seed data is opt-in | Re-run migrations with `INCLUDE_SEEDS=true` (never on a real deployment) |
| "has tables but no migration history" | Database was migrated before migrations were tracked | Recreate it, or re-run with `MIGRATIONS_BASELINE` set to the last migration it has (this keeps any damage from earlier re-runs) |

---

## Config Files

| File | Purpose |
|------|---------|
| `railway.json` | Railway build/deploy config |
| `Procfile` | Heroku-style start command |
| `python-packages/dataing/scripts/migrate-prod.sh` | Run DB migrations against production |
| `python-packages/dataing/migrations/*.sql` | Database schema migrations |
| `frontend/vercel.json` | Vercel build config |
| `frontend/.env.example` | Frontend env var template |
