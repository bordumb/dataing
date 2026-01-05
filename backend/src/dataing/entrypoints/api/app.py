"""FastAPI application definition."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .deps import lifespan
from .routes import api_router

app = FastAPI(
    title="dataing",
    description="Autonomous Data Quality Investigation",
    version="2.0.0",
    lifespan=lifespan,
    redirect_slashes=False,  # Prevent 307 redirects that lose auth headers
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}
