"""
Entrypoint for Vercel FastAPI service.
Exports the FastAPI app instance from app.main.
"""
from app.main import app

__all__ = ["app"]

