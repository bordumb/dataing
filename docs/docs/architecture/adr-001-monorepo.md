# ADR-001: Monorepo Structure

## Status

Accepted

## Context

We need to organize the codebase for a system that includes:

- Python backend (FastAPI)
- TypeScript frontend (React/Vite)
- Shared documentation
- Infrastructure configuration

## Decision

Use a monorepo structure with clear separation:

```
/
├── backend/          # Python code
├── frontend/         # TypeScript/React code
├── docs/             # MkDocs documentation
├── infra/            # Docker, K8s configs
├── tests/            # Shared test fixtures
├── pyproject.toml    # Root Python config
├── justfile          # Universal task runner
└── .github/          # CI/CD workflows
```

## Rationale

1. **Single Source of Truth**: All code in one place
2. **Atomic Changes**: Frontend and backend changes can be committed together
3. **Shared CI/CD**: One workflow can run all tests
4. **Simple Dependencies**: No need for private package registries

## Consequences

### Positive

- Easier code review across stack
- Consistent tooling (just, prettier, etc.)
- Single git history

### Negative

- Larger repository size
- Need to be careful with CI caching
- Teams must coordinate on shared infrastructure

## Implementation

- Use `just` as the universal task runner
- Separate CI workflows for backend and frontend
- Path-based triggers for efficient CI
