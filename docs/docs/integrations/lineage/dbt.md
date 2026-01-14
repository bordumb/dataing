# dbt Integration

Connect dataing to dbt for enriched investigations with data lineage context.

---

## What It Enables

With dbt lineage, dataing can:

- **Trace upstream dependencies** - Find the source tables that feed into the anomalous table
- **Identify transformations** - See what SQL transformations were applied
- **Find related models** - Discover other tables that might be affected
- **Access column-level lineage** - Understand which columns flow from where

---

## Setup

### Upload manifest.json

dbt generates a `manifest.json` file containing model metadata and lineage. Upload it to dataing:

=== "CLI"

    ```bash
    # After running dbt compile or dbt run
    dataing lineage upload \
      --provider dbt \
      --file target/manifest.json
    ```

=== "Python SDK"

    ```python
    from dataing.adapters.lineage.dbt import DbtLineageProvider

    provider = DbtLineageProvider()
    provider.load_manifest("target/manifest.json")
    ```

=== "API"

    ```bash
    curl -X POST https://api.dataing.io/v1/lineage/dbt \
      -H "X-API-Key: your-api-key" \
      -F "manifest=@target/manifest.json"
    ```

### Auto-Refresh (CI/CD)

Add lineage upload to your dbt CI/CD pipeline:

```yaml
# GitHub Actions example
- name: Upload dbt lineage to dataing
  run: |
    dataing lineage upload \
      --provider dbt \
      --file target/manifest.json
  env:
    DATAING_API_KEY: ${{ secrets.DATAING_API_KEY }}
```

---

## What's Extracted

From `manifest.json`, dataing extracts:

| Data | Source | Usage |
|------|--------|-------|
| Model names | `nodes.*.name` | Table identification |
| Dependencies | `nodes.*.depends_on` | Upstream lineage |
| SQL | `nodes.*.raw_code` | Transformation context |
| Columns | `nodes.*.columns` | Column-level lineage |
| Tests | `nodes.*.tests` | Quality context |
| Descriptions | `nodes.*.description` | Documentation |

---

## Integration Points

### During Context Gathering

When dataing investigates an anomaly, it queries dbt lineage:

```python
# Example lineage context
{
    "table": "orders",
    "upstream": [
        {"name": "raw_checkout_events", "type": "source"},
        {"name": "stg_users", "type": "model"},
    ],
    "downstream": [
        {"name": "fct_daily_orders", "type": "model"},
        {"name": "rpt_revenue", "type": "model"},
    ],
    "transformations": [
        "COALESCE(user_id, guest_id) AS user_id",
        "CASE WHEN status = 'completed' THEN 1 ELSE 0 END AS is_complete"
    ]
}
```

### Hypothesis Generation

Lineage context helps the LLM generate better hypotheses:

> "The `orders.user_id` column comes from `stg_users.user_id` via a LEFT JOIN.
> A NULL spike could indicate:
> 1. `stg_users` has missing records
> 2. The JOIN key changed
> 3. Upstream `raw_users` had data quality issues"

---

## Supported dbt Versions

| dbt Version | manifest.json Version | Status |
|-------------|----------------------|--------|
| 1.5+ | v10+ | :material-check-circle:{ .green } |
| 1.4 | v9 | :material-check-circle:{ .green } |
| 1.3 | v8 | :material-check-circle:{ .green } |
| <1.3 | v7 and below | :material-clock-outline: Limited |

---

## Column-Level Lineage

If your dbt project has column-level lineage enabled:

```yaml
# dbt_project.yml
vars:
  dbt_column_lineage: true
```

dataing can trace specific columns:

```python
# Column lineage context
{
    "column": "user_id",
    "source_columns": [
        {"table": "raw_users", "column": "id"},
        {"table": "raw_checkout", "column": "customer_id"}
    ],
    "transformations": [
        "COALESCE(u.id, c.customer_id)"
    ]
}
```

---

## Troubleshooting

### "Manifest file not found"

Ensure you've run `dbt compile` or `dbt run` first:

```bash
cd your-dbt-project
dbt compile
ls target/manifest.json
```

### "Model not found in lineage"

Check that:

- The model exists in your dbt project
- The manifest is up to date
- The model name matches exactly (case-sensitive)

### Stale Lineage

Set up automatic refresh in CI/CD, or manually refresh:

```bash
dataing lineage refresh --provider dbt
```

---

## Learn More

- [DataHub Integration](datahub.md)
- [How Investigations Work](../../concepts/investigations.md)
- [Architecture](../../architecture.md)
