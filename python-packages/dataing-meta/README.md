# Dataing

Autonomous Data Quality Investigation.

Dataing automatically detects and diagnoses data anomalies by gathering context, generating hypotheses with LLMs, testing them via SQL queries in parallel, and synthesizing findings into root cause analysis.

## Installation

Install everything:

```bash
pip install dataing[all]
```

Or install individual components:

```bash
pip install dataing[cli]      # CLI tool for terminal workflows
pip install dataing[sdk]      # Python SDK for programmatic access
pip install dataing[notebook] # Jupyter notebook integration
```

## Components

### CLI (`dataing-cli`)

Command-line interface for managing investigations:

```bash
dataing run start --name "Revenue drop" --question "Why did revenue drop 40%?"
dataing run status inv_abc123
dataing run list --status completed
```

### SDK (`dataing-sdk`)

Python SDK for programmatic access:

```python
from dataing_sdk import DataingClient

client = DataingClient(api_key="your-api-key")
investigation = client.start_investigation(
    name="Revenue drop",
    question="Why did revenue drop 40%?"
)
```

### Notebook (`dataing-notebook`)

Jupyter notebook widgets for interactive investigation:

```python
from dataing_notebook import InvestigationWidget

widget = InvestigationWidget(investigation_id="inv_abc123")
widget.display()
```

## Requirements

- Python 3.10+
- A running Dataing backend instance

## Links

- [Documentation](https://github.com/bordumb/dataing#readme)
- [GitHub Repository](https://github.com/bordumb/dataing)
