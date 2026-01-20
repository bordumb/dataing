# dataing-notebook

Dataing notebook extension with IPython magics for data quality investigation.

## Installation

```bash
pip install dataing-notebook
```

## Usage

Load the extension in your Jupyter notebook:

```python
%load_ext dataing_notebook
```

### Connect to API

```python
%dataing connect --api-key sk-xxx --base-url https://api.dataing.io
```

### Attach Context

By URN:
```python
%dataing attach postgres://db.schema.orders
```

From SQL query:
```python
%dataing attach "SELECT * FROM orders" --datasource ds-123
```

### Display Lineage

```python
%dataing lineage
```

### Start Investigation

```python
%dataing ask "Why are there null values in the orders table?"
```

### Status and Management

```python
%dataing status  # Show current context
%dataing clear   # Clear context
```

## Features

- Context persistence across cell executions
- Server-derived bundle_hash for caching
- Rich output with optional `rich` library
- SSE streaming for investigation progress
