# Deployment

## Architecture

| Component | Platform | URL |
|-----------|----------|-----|
| Frontend | Vercel | `https://dataing.dev` |
| Backend | Railway | `https://dataing-production.up.railway.app` |
| Database | Railway PostgreSQL | Internal networking |

---

## Backend (Railway)

URL: https://railway.com/project/5b7c7807-517c-451b-9408-03c13ca2b2ca

### 1. Create Project

```bash
npm install -g @railway/cli
railway login
railway init
```

### 2. Add PostgreSQL

Railway Dashboard → **+ New** → **Database** → **PostgreSQL**

### 3. Link Database to Backend

Backend service → **Variables** → **Add Variable**:

```
DATABASE_URL = ${{Postgres.DATABASE_URL}}
```

### 4. Run Database Migrations

The PostgreSQL database needs tables created. Run migrations from your local machine:

```bash
# Get DATABASE_URL from Railway: PostgreSQL service → Connect → Copy URL
export DATABASE_URL="postgresql://postgres:xxx@xxx.railway.app:5432/railway"  # pragma: allowlist secret

# Run migrations
./dataing/scripts/migrate-prod.sh
```

This runs all SQL files in `dataing/migrations/` to create tables for auth, tenants, investigations, etc.

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
| "No tables" in Railway Postgres | Migrations not run | Run `./dataing/scripts/migrate-prod.sh` |
| Auth errors after deploy | Missing seed data | Migrations include demo seed data; re-run migrations |

---

## Config Files

| File | Purpose |
|------|---------|
| `railway.json` | Railway build/deploy config |
| `Procfile` | Heroku-style start command |
| `dataing/scripts/migrate-prod.sh` | Run DB migrations against production |
| `dataing/migrations/*.sql` | Database schema migrations |
| `frontend/vercel.json` | Vercel build config |
| `frontend/.env.example` | Frontend env var template |
