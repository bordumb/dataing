# @dataing/jupyterlab-dataing

JupyterLab extension for Dataing data quality investigation.

## Features

- **Status Bar Widget**: Shows connection state to the Dataing backend
- **Settings Panel**: Configure backend URL and other options
- **Auto-connect**: Automatically connects to the backend on startup
- **Periodic Health Checks**: Monitors connection status

## Requirements

- JupyterLab >= 4.0.0
- dataing-notebook (Python package with server extension)

## Installation

The JupyterLab extension is bundled with the dataing-notebook Python package:

```bash
pip install dataing-notebook
```

This installs both the server extension (for API proxying) and the JupyterLab frontend extension.

### Development Installation

For development, install the packages in editable mode:

```bash
# Install the Python server extension
cd python-packages/dataing-notebook
pip install -e .

# Build and install the JupyterLab extension
cd frontend/jupyterlab-dataing
jlpm install
jlpm build
jupyter labextension develop . --overwrite
```

## Configuration

### Backend Configuration

Set the backend URL via environment variable:

```bash
export DATAING_BACKEND_URL=http://localhost:8000
export DATAING_API_KEY=your_api_key
```

### JupyterLab Settings

Settings are available in JupyterLab's Advanced Settings:
Settings > Advanced Settings Editor > Dataing

Available settings:
- **Backend URL**: URL of the Dataing API server (default: http://localhost:8000)
- **Auto Connect**: Automatically connect on startup (default: true)
- **Connection Check Interval**: Health check interval in seconds (default: 30)
- **Show Status Bar**: Show connection status widget (default: true)

## Status Bar States

The status bar indicator shows the current connection state:
- **Green**: Connected to backend
- **Gray**: Disconnected
- **Blue (pulsing)**: Checking connection
- **Red**: Connection error

Click the status bar to see details and configuration instructions.

## Architecture

The extension uses a server-side proxy pattern for security:

1. **Frontend**: JupyterLab extension checks connection via server extension
2. **Server Extension**: Proxies requests to Dataing backend with API key injection
3. **Backend**: Dataing API server

This keeps API keys server-side and avoids CORS issues.

## Development

```bash
# Install dependencies
jlpm install

# Build the extension
jlpm build

# Watch for changes
jlpm watch

# Link for development
jupyter labextension develop . --overwrite
```

## License

Apache-2.0
