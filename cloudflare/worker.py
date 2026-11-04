"""Cloudflare Python Worker entrypoint for the Neural FastAPI service."""

import logging

logging.basicConfig(level=logging.WARNING)

# Load the Pyodide-compatible driver during startup, not on the first DB request.
import asyncpg  # noqa: F401

from workers import asgi

from app.api import app

# Cloudflare's Python Worker runtime supplies the ASGI server and request env scope.
Default = asgi.entrypoint(app)
