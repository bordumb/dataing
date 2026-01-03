
## Testing Strategy

For each new feature, create:

1. **Unit tests** - Core business logic
2. **Integration tests** - Database operations
3. **API tests** - Route handlers

Example test structure:
```
tests/
├── unit/
│   ├── test_auth_service.py
│   ├── test_usage_tracker.py
│   └── ...
├── integration/
│   ├── test_api_keys.py
│   ├── test_data_sources.py
│   └── ...
├── e2e/
│   └── test_investigation_flow.py
└── fixtures/
    ├── api_keys.py
    └── data_sources.py
```

We need unit tests for all of these:
```
/Users/bordumb/workspace/repositories/dataing
└── backend
    └── src
        └── dataing
            ├── adapters
            │   ├── context
            │   │   ├── __init__.py
            │   │   ├── engine.py
            │   │   └── lineage.py
            │   ├── db
            │   │   ├── __init__.py
            │   │   ├── app_db.py
            │   │   ├── mock.py
            │   │   ├── postgres.py
            │   │   └── trino.py
            │   ├── llm
            │   │   ├── __init__.py
            │   │   ├── client.py
            │   │   └── prompt_manager.py
            │   ├── notifications
            │   │   ├── __init__.py
            │   │   ├── email.py
            │   │   ├── slack.py
            │   │   └── webhook.py
            │   └── __init__.py
            ├── core
            │   ├── __init__.py
            │   ├── domain_types.py
            │   ├── exceptions.py
            │   ├── interfaces.py
            │   ├── orchestrator.py
            │   └── state.py
            ├── entrypoints
            │   ├── api
            │   │   ├── middleware
            │   │   │   ├── __init__.py
            │   │   │   ├── audit.py
            │   │   │   ├── auth.py
            │   │   │   └── rate_limit.py
            │   │   ├── routes
            │   │   │   ├── __init__.py
            │   │   │   ├── approvals.py
            │   │   │   ├── dashboard.py
            │   │   │   ├── datasources.py
            │   │   │   ├── investigations.py
            │   │   │   ├── settings.py
            │   │   │   └── users.py
            │   │   ├── __init__.py
            │   │   ├── app.py
            │   │   ├── deps.py
            │   │   └── routes.py
            │   ├── mcp
            │   │   ├── __init__.py
            │   │   └── server.py
            │   └── __init__.py
            ├── models
            │   ├── __init__.py
            │   ├── api_key.py
            │   ├── audit_log.py
            │   ├── base.py
            │   ├── data_source.py
            │   ├── investigation.py
            │   ├── tenant.py
            │   ├── user.py
            │   └── webhook.py
            ├── prompts
            │   ├── hypothesis.yaml
            │   ├── interpretation.yaml
            │   ├── query.yaml
            │   ├── reflexion.yaml
            │   └── synthesis.yaml
            ├── safety
            │   ├── __init__.py
            │   ├── circuit_breaker.py
            │   ├── pii.py
            │   └── validator.py
            ├── services
            │   ├── __init__.py
            │   ├── auth.py
            │   ├── notification.py
            │   ├── tenant.py
            │   └── usage.py
            └── __init__.py
```
