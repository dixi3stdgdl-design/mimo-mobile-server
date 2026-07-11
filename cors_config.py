"""CORS configuration for HTTP endpoints."""

import os


def get_cors_origins() -> list[str]:
    """Get allowed CORS origins from environment or defaults."""
    env_val = os.environ.get("MIMO_CORS_ORIGINS", "")
    if env_val:
        return [o.strip() for o in env_val.split(",") if o.strip()]
    return ["*"]


CORS_ORIGINS = get_cors_origins()
CORS_ALLOW_METHODS = "GET, POST, PUT, DELETE, OPTIONS"
CORS_ALLOW_HEADERS = "Content-Type, Authorization, X-Request-ID"
CORS_MAX_AGE = "86400"


def apply_cors_headers(handler, origin: str | None = None):
    """Apply CORS headers to an HTTP request handler."""
    allowed = CORS_ORIGINS
    if "*" in allowed:
        handler.send_header("Access-Control-Allow-Origin", "*")
    elif origin and origin in allowed:
        handler.send_header("Access-Control-Allow-Origin", origin)
    elif allowed:
        handler.send_header("Access-Control-Allow-Origin", allowed[0])

    handler.send_header("Access-Control-Allow-Methods", CORS_ALLOW_METHODS)
    handler.send_header("Access-Control-Allow-Headers", CORS_ALLOW_HEADERS)
    handler.send_header("Access-Control-Max-Age", CORS_MAX_AGE)
