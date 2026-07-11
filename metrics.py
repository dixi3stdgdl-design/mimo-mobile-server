"""Prometheus metrics collector."""

import time
import threading
from prometheus_client import (
    Gauge, Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
)


WS_CONNECTIONS = Gauge(
    "mimo_ws_connections_active",
    "Number of active WebSocket connections"
)

WS_MESSAGES = Counter(
    "mimo_ws_messages_total",
    "Total WebSocket messages received",
    ["msg_type"]
)

WS_AUTH_FAILURES = Counter(
    "mimo_ws_auth_failures_total",
    "Total authentication failures"
)

HTTP_REQUESTS = Counter(
    "mimo_http_requests_total",
    "Total HTTP requests",
    ["path", "method", "status"]
)

HTTP_REQUEST_DURATION = Histogram(
    "mimo_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

CHAT_COMMANDS = Counter(
    "mimo_chat_commands_total",
    "Total chat commands executed"
)

ACTIVE_PROCESSES = Gauge(
    "mimo_active_processes",
    "Number of active subprocess processes"
)

SCREEN_FRAMES = Counter(
    "mimo_screen_frames_total",
    "Total screen frames captured"
)

UPTIME = Gauge(
    "mimo_uptime_seconds",
    "Server uptime in seconds"
)

_start_time = time.time()


def _uptime_updater():
    while True:
        UPTIME.set(time.time() - _start_time)
        time.sleep(10)


def start_uptime_thread():
    t = threading.Thread(target=_uptime_updater, daemon=True)
    t.start()


def get_metrics():
    return generate_latest()


METRICS_CONTENT_TYPE = CONTENT_TYPE_LATEST
