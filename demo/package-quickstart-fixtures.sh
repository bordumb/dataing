#!/bin/bash
# Package demo fixtures subset for quickstart guide
# Creates demo-fixtures.tar.gz with baseline, null_spike, and volume_drop scenarios
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTDIR="demo-fixtures"

cd "$SCRIPT_DIR"

# Clean previous build
rm -rf "$OUTDIR" "$OUTDIR.tar.gz"
mkdir -p "$OUTDIR"

echo "Packaging quickstart fixtures..."

# Copy selected scenarios (minimal set for quickstart)
# Exclude events.parquet (18MB each) - not needed for quickstart investigations
for scenario in baseline null_spike volume_drop; do
  mkdir -p "$OUTDIR/$scenario"
  for file in "fixtures/$scenario"/*.parquet; do
    filename=$(basename "$file")
    # Skip events.parquet to reduce tarball size
    if [ "$filename" != "events.parquet" ]; then
      cp "$file" "$OUTDIR/$scenario/"
    fi
  done
  # Copy manifest if present
  if [ -f "fixtures/$scenario/manifest.json" ]; then
    cp "fixtures/$scenario/manifest.json" "$OUTDIR/$scenario/"
  fi
done

# Copy the quickstart loader
cp quickstart-load.sql "$OUTDIR/load_duckdb.sql"

# Create README
cat > "$OUTDIR/README.md" << 'EOF'
# Dataing Quickstart Fixtures

Pre-seeded e-commerce data with anomalies for the Dataing quickstart guide.

## Scenarios

| Scenario | Description |
|----------|-------------|
| `baseline` | Clean data, no anomalies |
| `null_spike` | Mobile app bug causes NULL user_id spike (primary quickstart scenario) |
| `volume_drop` | Weekend traffic drop in orders |

## Quick Start

```bash
# Load the null_spike scenario (default)
duckdb demo.db < load_duckdb.sql

# Verify
duckdb demo.db -c "SELECT COUNT(*) FROM orders;"
```

## Loading Different Scenarios

Edit `load_duckdb.sql` and change the `fixture` variable:

```sql
SET VARIABLE fixture = 'volume_drop';  -- or 'baseline'
```

## Tables

- `users` - Customer accounts
- `categories` - Product categories
- `products` - E-commerce products
- `orders` - Customer orders
- `order_items` - Line items per order

> **Note**: The `events` table is excluded from the quickstart package to reduce download size.
> Full fixtures with all tables are available in the repository at \`demo/fixtures/\`.
EOF

# Create tarball
tar czf "$OUTDIR.tar.gz" "$OUTDIR"

# Report size
SIZE=$(du -h "$OUTDIR.tar.gz" | cut -f1)
echo "Created demo-fixtures.tar.gz ($SIZE)"

# Cleanup build directory
rm -rf "$OUTDIR"

echo "Done!"
