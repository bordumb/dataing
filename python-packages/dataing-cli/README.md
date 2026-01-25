# dataing-cli

Command-line interface for Dataing - the autonomous data quality investigation platform.

## Installation

```bash
pip install dataing-cli
```

## Usage

```bash
# Initialize configuration
dataing init

# Check connection status
dataing status

# Start an investigation
dataing run start my_table --goal "investigate anomaly"

# Manage datasources
dataing ds list
dataing ds attach <datasource-id>
```

## Development

```bash
# Install in dev mode
uv pip install -e ".[dev]"

# Run tests
pytest
```
