# Datasource Resolution

This document describes how Dataing resolves which datasource to use when executing queries and investigations.

## Overview

When you have multiple datasources configured (e.g., staging vs production, US vs EU regions, or different database clusters), Dataing needs to know which one to query. The resolution follows a clear precedence order to ensure predictable behavior.

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

### 2. Asset-Level `datasource_id`

When an asset includes a `datasource_id`, that binding is respected:

```python
# Asset with datasource binding
client.ask(
    "Check data quality",
    assets=[
        AssetRef(
            platform="postgres",
            name="analytics.orders",
            datasource_id="ds_prod"  # Asset-level binding
        )
    ]
)
```

This is useful when working with multiple datasources in the same request.

### 3. Session/Context Default

In notebooks and SDK sessions, you can set a default datasource:

```python
# SDK
client.attach("ds_prod")  # Sets session default

# Notebook magic
%dataing attach postgres://analytics.orders --datasource-id ds_prod
```

Subsequent requests use this default unless overridden.

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
    "message": "Multiple datasources match platform 'postgres'. Please specify which to use.",
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
    "hint": "Specify datasource_id in your request or use '%dataing attach' to set a session default"
}
```

## Visibility

The bound datasource is always visible:

### SDK

```python
>>> bundle = client.bundle(assets=[...])
>>> bundle
ContextBundle(datasource_id='ds_prod', assets=['analytics.orders'])
```

### Notebook Magics

```
In [1]: %dataing attach postgres://analytics.orders --datasource-id ds_prod
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
2. **In Development**: Use `%dataing attach` to set a session default
3. **In Scripts**: Pass `datasource_id` to `client.ask()` or `client.bundle()`
4. **With Multiple Regions**: Include `datasource_id` at the asset level

## Troubleshooting

### "Multiple datasources match"

You have multiple datasources with the same platform. Options:

1. Add `datasource_id` to your request
2. Use `%dataing attach` to set a default
3. Use asset-level binding for multi-datasource queries

### "No datasource found"

Your tenant doesn't have a datasource for that platform. Check:

1. The platform name is correct (e.g., `postgres` not `postgresql`)
2. The datasource is configured for your tenant
3. Your API key has access to the datasource
