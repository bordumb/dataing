"""Railway/deployment entrypoint.

This file exists for Railway/Heroku auto-detection.
It imports the FastAPI app from the proper location.
"""

from dataing.entrypoints.api.app import app

__all__ = ["app"]
