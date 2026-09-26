# dataing

Community Edition backend for Dataing, the autonomous data quality investigation platform.

Dataing detects and diagnoses data anomalies. It gathers context, generates hypotheses with LLMs, tests them with SQL queries in parallel, and synthesizes the findings into a root cause analysis.

This package contains the FastAPI API server and the Temporal worker that runs investigations. To work with a running backend, use the client packages instead: `dataing-cli`, `dataing-sdk`, and `dataing-notebook`.

## Running

Both processes are configured through environment variables such as `DATABASE_URL`, `TEMPORAL_HOST`, and `ANTHROPIC_API_KEY`. The repository's `docker-compose.yml` shows a complete setup.

```bash
# API server
uvicorn dataing.entrypoints.api.app:app --host 0.0.0.0 --port 8000

# Temporal worker
python -m dataing.entrypoints.temporal_worker
```

To run the full stack, run `docker compose up` from the repository root.

## Links

- [GitHub Repository](https://github.com/bordumb/dataing)
- [Deployment Guide](https://github.com/bordumb/dataing/blob/main/docs/docs/development/deployment.md)
