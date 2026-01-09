#!/usr/bin/env python
"""Export OpenAPI schema from FastAPI app for frontend code generation."""

import json
import sys
from pathlib import Path

# Add the src directory to the path so we can import the app
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dataing.entrypoints.api.app import app


def main() -> None:
    """Export OpenAPI schema to JSON file."""
    output_path = Path(__file__).parent.parent / "openapi.json"
    schema = app.openapi()

    with open(output_path, "w") as f:
        json.dump(schema, f, indent=2)

    print(f"OpenAPI schema exported to {output_path}")


if __name__ == "__main__":
    main()
