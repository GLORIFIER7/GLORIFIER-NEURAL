"""Cloudflare Python Worker entrypoint for the Neural FastAPI service."""

from workers import asgi

from app.api import app

# Cloudflare's Python Worker runtime supplies the ASGI server and request env scope.
Default = asgi.entrypoint(app)
