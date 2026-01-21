# Datasource Resolution

This document describes how Dataing resolves which datasource to use when executing queries and investigations.

## Overview

When you have multiple datasources configured (e.g., staging vs production, US vs EU regions, or different database clusters), Dataing needs to know which one to query. The resolution follows a clear precedence order to ensure predictable behavior.

## Key Principle: Asset URNs Never Include Datasource ID

- Asset URN: `analytics.orders` or `analytics.orders.customer_id`
- Datasource is resolved **separately**, never embedded in URN
- This keeps URNs portable and human-readable

Why? Because the same asset (e.g., `analytics.orders`) might exist in both staging and production. The datasource tells you *which copy* to query, but the URN identifies *what* you're querying.

## Precedence Rules

Datasource resolution follows this order (highest to lowest priority):

### 1. Explicit `datasource_id` in Request

When you explicitly provide a `datasource_id` in an API request, it always wins:

```python
# SDK
client.ask(
    "Why did null_rate spike?",
    assets=[AssetRef(platform="postgres", name="analytics.orders")],
    datasource_id="ds_12345"  # Explicit - always used
)

# API
POST /api/v1/runs
{
    "goal": "Why did null_rate spike?",
    "bundle": {
        "assets": [{"platform": "postgres", "name": "analytics.orders"}]
    },
    "datasource_id": "ds_12345"  # Explicit
}
```

### 2. Asset-Level Binding (from `attach()`)

When you call `attach()`, it binds your session context to a datasource. This binding is used for subsequent requests:

```python
# SDK - attach binds context to asset, resolving datasource
client.attach("ds_prod", name="Production Analytics")

# Notebook magic - same semantics
%dataing attach analytics.orders --datasource-id ds_prod
```

**Note**: `attach` is "bind context to an asset" not "choose a database." The datasource is a side effect of knowing which asset you're investigating. This reinforces that datasource IDs are internal implementation details.

### 3. Session/Context Default

If you've called `attach()` but not specified a datasource in the current request, the session default is used:

```python
# After attach, all requests use the session default
client.attach("ds_prod")
client.ask("Check data quality", assets=[...])  # Uses ds_prod
```

### 4. Single Datasource for Tenant

If your tenant has exactly one datasource configured, it's used automatically:

```python
# No need to specify - uses the only datasource available
client.ask("Check data quality", assets=[...])
```

### 5. Ambiguous (409 Conflict)

If none of the above apply and multiple datasources match, the API returns a 409 Conflict error with available options:

```json
{
    "error": "ambiguous_datasource",
    "message": "Multiple datasources available. Please specify which to use.",
    "available_datasources": [
        {
            "id": "ds_prod",
            "name": "Production Analytics",
            "platform": "postgres",
            "host": "prod.db.example.com"
        },
        {
            "id": "ds_staging",
            "name": "Staging Analytics",
            "platform": "postgres",
            "host": "staging.db.example.com"
        }
    ],
    "hint": "Specify datasource_id in your request or use '%dataing attach <asset>' to bind context"
}
```

## Visibility

The bound datasource is always visible to prevent confusion:

### SDK

```python
>>> client.attach("ds_prod", name="Production Analytics")
>>> client
DataingClient(base_url='http://localhost:8000', datasource='Production Analytics (ds_prod)')

>>> bundle = client.bundle(assets=[...])
>>> bundle
ContextBundle(datasource_id='ds_prod', assets=['analytics.orders'])
```

### Notebook Magics

```
In [1]: %dataing attach analytics.orders --datasource-id ds_prod
Attached to ds_prod (Production Analytics)

In [2]: %dataing status
Connected to: http://localhost:8000
Datasource: ds_prod (Production Analytics)
```

### Run Events

All SSE events include the bound datasource:

```json
{
    "event": "run_started",
    "data": {
        "run_id": "...",
        "datasource_id": "ds_prod",
        "datasource_name": "Production Analytics"
    }
}
```

## Best Practices

1. **In Production**: Always use explicit `datasource_id` to avoid ambiguity
2. **In Development**: Use `%dataing attach` to bind context for your session
3. **In Scripts**: Pass `datasource_id` to `client.ask()` or `client.bundle()`
4. **For Debugging**: Check `client.__repr__()` to see the bound datasource

## Troubleshooting

### "Multiple datasources available"

You have multiple datasources and none has been selected. Options:

1. Add `datasource_id` to your request
2. Use `%dataing attach` or `client.attach()` to bind context
3. Check the 409 response for available datasources with their IDs

### "No datasource found"

Your tenant doesn't have a datasource for that platform. Check:

1. The platform name is correct (e.g., `postgres` not `postgresql`)
2. The datasource is configured for your tenant
3. Your API key has access to the datasource
