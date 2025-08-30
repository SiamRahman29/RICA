"""API endpoints for the RICA."""

from .server import create_app
from .routes import router

__all__ = ["create_app", "router"]
