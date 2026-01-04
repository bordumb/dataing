# Dataing

Autonomous Data Quality Investigation - an AI-powered system that automatically detects and diagnoses data anomalies.

## Prerequisites

- Python 3.11+
- Node.js 18+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [pnpm](https://pnpm.io/) (Node package manager)
- [just](https://github.com/casey/just) (command runner)

```bash
# Install prerequisites on macOS
brew install uv pnpm just
```

## Installation

```bash
# Clone and setup
git clone <repo-url>
cd dataing

# Install all dependencies
just setup
```

## Demo

Run a complete demo with pre-loaded e-commerce data containing anomalies:

```bash
just demo
```

This starts:
- Backend at http://localhost:8000
- Frontend at http://localhost:3000

Demo API key: `dd_demo_12345`

See [demo/README.md](demo/README.md) for more details on the demo fixtures and scenarios.

## Development

```bash
# Run backend + frontend in dev mode
just dev

# Run just backend
just dev-backend

# Run just frontend
just dev-frontend

# Run tests
just test

# Run linters
just lint
```

## Project Structure

```
dataing/
├── backend/          # FastAPI backend (Python)
├── frontend/         # Next.js frontend (TypeScript)
├── demo/             # Demo fixtures and data generator
└── docs/             # Documentation
```

See [frontend/README.md](frontend/README.md) for frontend-specific documentation.
