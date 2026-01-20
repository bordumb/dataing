# dataing-sdk

Python SDK for Dataing - data quality investigation platform.

## Installation

```bash
# Basic install
pip install dataing-sdk

# With SSE streaming support
pip install "dataing-sdk[streaming]"

# With SQL parsing support
pip install "dataing-sdk[sql]"

# All extras
pip install "dataing-sdk[all]"
```

## Quick Start

```python
from dataing_sdk import DataingClient, AssetRef

# Create client
client = DataingClient(
    base_url="https://api.dataing.io",
    api_key="your-api-key"
)

# Reference assets
orders = AssetRef(platform="postgres", name="ecommerce.public.orders")
customers = AssetRef(platform="postgres", name="ecommerce.public.customers")

# Run investigation
run = client.run(
    assets=[orders, customers],
    goal="Why did order counts drop 40% yesterday?"
)

# Stream events
for event in run.events():
    print(event)
```

## API Reference

See the full documentation at https://docs.dataing.io/sdk
