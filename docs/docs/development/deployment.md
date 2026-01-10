# Deployment

## Architecture

| Component | Platform | URL |
|-----------|----------|-----|
| Frontend | Vercel | `https://your-app.vercel.app` |
| Backend | Railway | `https://your-app.up.railway.app` |
| Database | Railway PostgreSQL | Internal networking |

---

## Backend (Railway)

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

### 4. Add Required Env Vars

| Variable | Value |
|----------|-------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key |

### 5. Enable Public URL

**Settings** → **Networking** → **Generate Domain**

### 6. Deploy

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
| `VITE_API_URL` | `https://your-railway-url.up.railway.app` |

**Important**: No trailing slash.

### 3. Deploy

Vercel auto-deploys on push to `main`.

Manual redeploy: **Deployments** → **...** → **Redeploy**

After changing env vars, redeploy with **"Use existing Build Cache" = OFF**.

---

## Verification

### Backend Health

```bash
curl https://your-railway-url.up.railway.app/health
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
| `HTTP 405` on login | Frontend calling Vercel not Railway | Set `VITE_API_URL` in Vercel, redeploy |
| `Connection refused` on startup | Postgres not ready | Retry logic handles this; check DB is provisioned |
| `Distribution not found: bond` | Deploying from wrong root | Deploy from repo root, not `dataing/` |
| TypeScript build errors | Missing generated files | Ensure `frontend/src/lib/api/generated/` is in git |

---

## Config Files

| File | Purpose |
|------|---------|
| `railway.json` | Railway build/deploy config |
| `Procfile` | Heroku-style start command |
| `frontend/vercel.json` | Vercel build config |
| `frontend/.env.example` | Frontend env var template |
