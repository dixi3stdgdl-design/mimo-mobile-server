"""Structured JSON logging configuration."""

import json
import logging
import sys
import time
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Formats log records as structured JSON."""

    def format(self, record):
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        if hasattr(record, "method"):
            log_entry["method"] = record.method
        if hasattr(record, "path"):
            log_entry["path"] = record.path
        if hasattr(record, "status"):
            log_entry["status"] = record.status
        if hasattr(record, "duration_ms"):
            log_entry["duration_ms"] = record.duration_ms
        if hasattr(record, "ip"):
            log_entry["ip"] = record.ip
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)


def setup_logging(level: str = "INFO"):
    """Configure structured JSON logging for the server."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)

    # Quiet noisy libraries
    logging.getLogger("prometheus_client").setLevel(logging.WARNING)


def log_request(method: str, path: str, status: int, duration_ms: float, ip: str):
    """Emit a structured request log entry."""
    logger = logging.getLogger("mimo.http")
    extra = {
        "method": method,
        "path": path,
        "status": status,
        "duration_ms": round(duration_ms, 2),
        "ip": ip,
    }
    logger.info(f"{method} {path} {status} {duration_ms:.1f}ms", extra=extra)
