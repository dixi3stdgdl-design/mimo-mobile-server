"""Gunicorn configuration for multi-worker deployment."""

import os
import multiprocessing

bind = f"0.0.0.0:{os.environ.get('MIMO_WS_PORT', '8765')}"
workers = int(os.environ.get("MIMO_WORKERS", str(multiprocessing.cpu_count())))
worker_class = "uvicorn.workers.UvicornWorker"
timeout = 120
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = "info"
preload_app = False
