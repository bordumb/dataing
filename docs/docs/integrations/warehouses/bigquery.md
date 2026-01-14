# BigQuery Integration

Connect dataing to Google BigQuery for AI-powered data quality investigations.

---

## Prerequisites

- Google Cloud project with BigQuery enabled
- Service account with BigQuery read access
- BigQuery Data Viewer role (or custom role with equivalent permissions)

### Recommended Permissions

Create a service account with minimal permissions:

```bash
# Create service account
gcloud iam service-accounts create dataing-reader \
  --display-name="dataing Data Reader"

# Grant BigQuery Data Viewer role
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:dataing-reader@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataViewer"

# Grant BigQuery Job User (to run queries)
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:dataing-reader@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"

# Download credentials
gcloud iam service-accounts keys create credentials.json \
  --iam-account=dataing-reader@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

---

## Configuration

=== "Environment Variables"

    ```bash
    export DATAING_DATASOURCE=bigquery
    export DATAING_BIGQUERY_PROJECT=your-project-id
    export DATAING_BIGQUERY_DATASET=your_dataset
    export GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
    ```

=== "Python SDK"

    ```python
    from dataing.adapters.datasource.sql.bigquery import BigQueryAdapter

    adapter = BigQueryAdapter(
        project_id="your-project-id",
        dataset="your_dataset",
        credentials_json=open("credentials.json").read(),
        location="US",
    )
    ```

### Configuration Fields

| Field | Required | Description |
|-------|----------|-------------|
| `project_id` | Yes | Google Cloud project ID |
| `dataset` | No | Default dataset (can query cross-dataset) |
| `credentials_json` | Yes | Service account credentials JSON |
| `location` | No | Query location (US, EU, or specific region) |

---

## Supported Features

| Feature | Status | Notes |
|---------|--------|-------|
| Schema Discovery | :material-check-circle:{ .green } | Full table/column metadata |
| Column Statistics | :material-check-circle:{ .green } | Via INFORMATION_SCHEMA |
| Query Execution | :material-check-circle:{ .green } | SELECT only |
| Partitioned Tables | :material-check-circle:{ .green } | Partition filter aware |
| Views | :material-check-circle:{ .green } | Including authorized views |
| External Tables | :material-check-circle:{ .green } | GCS, Drive sources |

---

## Troubleshooting

### "Permission denied"

Ensure service account has required roles:

```bash
# Check current permissions
gcloud projects get-iam-policy YOUR_PROJECT_ID \
  --filter="bindings.members:dataing-reader@"

# Add missing role
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:dataing-reader@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataViewer"
```

### "Dataset not found"

Check that:

- Dataset exists in the specified project
- Location matches dataset location
- Service account has access to dataset

---

## Learn More

- [Snowflake Integration](snowflake.md)
- [Architecture](../../architecture.md)
- [Security](../../security/data-privacy.md)
