# fn-23.1 Asset Instances Search API Endpoint - Done

## Summary

Implemented the cross-datasource asset instances search API endpoint at `GET /api/v1/asset-instances/search`.

## Changes

### New Files
- `python-packages/dataing/src/dataing/entrypoints/api/routes/asset_instances.py` - New route with search endpoint
- `python-packages/dataing/tests/unit/api/test_asset_instances_routes.py` - Route unit tests (8 tests)
- `python-packages/dataing/tests/unit/adapters/db/test_app_db_asset_search.py` - Database method tests (6 tests)

### Modified Files
- `python-packages/dataing/src/dataing/adapters/db/app_db.py` - Added `search_asset_instances()` method
- `python-packages/dataing/src/dataing/entrypoints/api/routes/__init__.py` - Registered new router

## API Contract

```
GET /api/v1/asset-instances/search
  ?q=<query>           # Required, min 1 char
  &limit=<int>         # Default 10, max 100
  &cursor=<string>     # Opaque pagination cursor
  &datasource_id=<id>  # Optional filter

Response:
{
  "results": [
    {
      "asset_urn": "urn:dataing:postgres:ds_prod:public.orders",
      "display_name": "orders",
      "type": "table",
      "schema_name": "public",
      "datasource_id": "ds_prod",
      "datasource_name": "Production Analytics",
      "platform": "postgres",
      "match_reason": "name_prefix"
    }
  ],
  "next_cursor": "..." | null,
  "total_hint": 42
}
```

## Acceptance Criteria Met
- [x] Endpoint created at `/api/v1/asset-instances/search`
- [x] Searches across all tenant datasources
- [x] Optional `datasource_id` filter
- [x] Cursor-based pagination
- [x] Returns asset_urn, display_name, type, schema, datasource context
- [x] Returns match_reason (name_prefix, path_match, fuzzy)
- [x] Unit tests pass (14 total)
- [x] TypeScript compiles without errors (Python equivalent: ruff + mypy pass)
