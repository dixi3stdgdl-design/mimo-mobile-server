"""HTTP request handler with rate limiting, CORS, logging, and metrics."""

import asyncio
import json
import subprocess
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from config import WS_PORT, HTTP_PORT, WORKSPACE, MIMO_SERVER_NAME, ADB_PATH, PROTOCOL_VERSION
from metrics import HTTP_REQUESTS, HTTP_REQUEST_DURATION, get_metrics, METRICS_CONTENT_TYPE
from analytics import get_analytics
from rate_limiter import get_rate_limiter
from cors_config import apply_cors_headers
from logging_config import log_request
from handlers.devin import handle_devin_webhook, get_session_status, list_sessions, cancel_session
from handlers.webhooks import handle_webhook, handle_github_webhook, get_recent_events, get_event_by_id


def create_http_handler(state):
    """Create HttpRequestHandler with bound state."""
    analytics = get_analytics()
    rate_limiter = get_rate_limiter()

    class HttpRequestHandler(SimpleHTTPRequestHandler):
        def _get_client_ip(self):
            forwarded = self.headers.get("X-Forwarded-For")
            if forwarded:
                return forwarded.split(",")[0].strip()
            return self.client_address[0]

        def _check_rate_limit(self):
            ip = self._get_client_ip()
            if not rate_limiter.is_allowed(ip):
                self.send_response(429)
                self.send_header("Content-Type", "application/json")
                self.send_header("Retry-After", "60")
                self.end_headers()
                body = json.dumps({"error": "Too Many Requests", "retry_after_seconds": 60})
                self.wfile.write(body.encode())
                return False
            return True

        def _send_json_response(self, status, body, path=None, method="GET"):
            ip = self._get_client_ip()
            origin = self.headers.get("Origin")

            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            apply_cors_headers(self, origin)
            self.end_headers()
            if isinstance(body, dict):
                body = json.dumps(body, indent=2)
            self.wfile.write(body.encode() if isinstance(body, str) else body)

            HTTP_REQUESTS.labels(path=path or self.path, method=method, status=str(status)).inc()

        def do_GET(self):
            start = time.monotonic()
            parsed = urlparse(self.path)
            path = parsed.path
            params = parse_qs(parsed.query)
            ip = self._get_client_ip()

            # ─── Health Check ─────────────────────────────────────
            if path == "/health":
                if not self._check_rate_limit():
                    return
                body = {
                    "status": "ok",
                    "version": PROTOCOL_VERSION,
                    "ws_port": WS_PORT,
                    "workspace": WORKSPACE,
                    "clients": state.client_count(),
                    "name": MIMO_SERVER_NAME,
                    "features": ["jwt_auth", "analytics", "tls"]
                }
                self._send_json_response(200, body, path="/health")

            # ─── Prometheus Metrics ────────────────────────────────
            elif path == "/metrics":
                self.send_response(200)
                self.send_header("Content-Type", METRICS_CONTENT_TYPE)
                self.end_headers()
                self.wfile.write(get_metrics())
                HTTP_REQUESTS.labels(path="/metrics", method="GET", status="200").inc()

            # ─── Dashboard Stats ────────────────────────────────
            elif path == "/api/dashboard":
                if not self._check_rate_limit():
                    return
                from metrics import UPTIME, WS_MESSAGES, CHAT_COMMANDS, ACTIVE_PROCESSES, SCREEN_FRAMES, WS_AUTH_FAILURES
                uptime_val = UPTIME._value.get() if hasattr(UPTIME, '_value') else 0
                dashboard = {
                    "status": "ok",
                    "server": MIMO_SERVER_NAME,
                    "version": PROTOCOL_VERSION,
                    "connections": {
                        "active": state.client_count(),
                        "total_authorized": len(state.authorized_devices),
                    },
                    "uptime_seconds": uptime_val,
                    "messages": {
                        "total": int(WS_MESSAGES._value.get()) if hasattr(WS_MESSAGES, '_value') else 0,
                        "chat_commands": int(CHAT_COMMANDS._value.get()) if hasattr(CHAT_COMMANDS, '_value') else 0,
                        "auth_failures": int(WS_AUTH_FAILURES._value.get()) if hasattr(WS_AUTH_FAILURES, '_value') else 0,
                    },
                    "processes": {
                        "active": int(ACTIVE_PROCESSES._value.get()) if hasattr(ACTIVE_PROCESSES, '_value') else 0,
                        "registered": len(state.processes),
                    },
                    "screen_frames": int(SCREEN_FRAMES._value.get()) if hasattr(SCREEN_FRAMES, '_value') else 0,
                    "streams_active": len(state.active_streams),
                    "workspace": WORKSPACE,
                }
                self._send_json_response(200, dashboard, path="/api/dashboard")

            # ─── Analytics API ─────────────────────────────────────
            elif path == "/api/analytics":
                if not self._check_rate_limit():
                    return
                days = int(params.get("days", ["7"])[0])
                report = analytics.export_report(days)
                self._send_json_response(200, report, path="/api/analytics")

            elif path == "/api/analytics/dau":
                if not self._check_rate_limit():
                    return
                days = int(params.get("days", ["30"])[0])
                dau = analytics.get_daily_active_users(days)
                self._send_json_response(200, dau, path="/api/analytics/dau")

            elif path == "/api/analytics/retention":
                if not self._check_rate_limit():
                    return
                days = int(params.get("days", ["30"])[0])
                retention = analytics.get_retention(days)
                self._send_json_response(200, retention[:100], path="/api/analytics/retention")

            elif path == "/api/analytics/features":
                if not self._check_rate_limit():
                    return
                days = int(params.get("days", ["7"])[0])
                features = analytics.get_feature_usage(days)
                self._send_json_response(200, features, path="/api/analytics/features")

            # ─── Command Execution ─────────────────────────────────
            elif path == "/api/exec":
                if not self._check_rate_limit():
                    return
                cmd = params.get("command", [""])[0]
                try:
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30, cwd=WORKSPACE)
                    body = {
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "returncode": result.returncode
                    }
                    self._send_json_response(200, body, path="/api/exec")
                except Exception as e:
                    self._send_json_response(500, {"error": str(e)}, path="/api/exec")

            # ─── ADB Endpoints ────────────────────────────────────
            elif path == "/api/adb/devices":
                if not self._check_rate_limit():
                    return
                try:
                    result = subprocess.run(
                        [ADB_PATH, "devices", "-l"],
                        capture_output=True, text=True, timeout=10
                    )
                    devices = []
                    for line in result.stdout.strip().split("\n")[1:]:
                        if line.strip() and "device" in line:
                            parts = line.split()
                            serial = parts[0]
                            state_val = parts[1] if len(parts) > 1 else "unknown"
                            model = ""
                            for p in parts[2:]:
                                if p.startswith("model:"):
                                    model = p.split(":")[1]
                            devices.append({"serial": serial, "state": state_val, "model": model})
                    self._send_json_response(200, {"devices": devices}, path="/api/adb/devices")
                except Exception as e:
                    self._send_json_response(500, {"error": str(e)}, path="/api/adb/devices")

            elif path == "/api/adb/exec":
                if not self._check_rate_limit():
                    return
                serial = params.get("serial", [""])[0]
                command = params.get("command", [""])[0]
                action = params.get("action", ["shell"])[0]
                if not serial or not command:
                    self._send_json_response(400, {"error": "serial and command required"}, path="/api/adb/exec")
                    return
                try:
                    if action == "shell":
                        result = subprocess.run(
                            [ADB_PATH, "-s", serial, "shell", command],
                            capture_output=True, text=True, timeout=30
                        )
                    elif action == "install":
                        result = subprocess.run(
                            [ADB_PATH, "-s", serial, "install", "-r", command],
                            capture_output=True, text=True, timeout=120
                        )
                    elif action == "push":
                        parts = command.split(" ", 1)
                        if len(parts) == 2:
                            result = subprocess.run(
                                [ADB_PATH, "-s", serial, "push", parts[0], parts[1]],
                                capture_output=True, text=True, timeout=60
                            )
                        else:
                            result = subprocess.CompletedProcess([], 1, stdout="", stderr="Usage: push local_path remote_path")
                    elif action == "pull":
                        parts = command.split(" ", 1)
                        if len(parts) == 2:
                            result = subprocess.run(
                                [ADB_PATH, "-s", serial, "pull", parts[0], parts[1]],
                                capture_output=True, text=True, timeout=60
                            )
                        else:
                            result = subprocess.CompletedProcess([], 1, stdout="", stderr="Usage: pull remote_path local_path")
                    elif action == "input":
                        input_type = params.get("input_type", ["text"])[0]
                        value = params.get("value", [""])[0]
                        if input_type == "text":
                            cmd = f"input text '{value}'"
                        elif input_type == "tap":
                            x, y = value.split(",")
                            cmd = f"input tap {x} {y}"
                        elif input_type == "keyevent":
                            cmd = f"input keyevent {value}"
                        elif input_type == "swipe":
                            x1, y1, x2, y2 = value.split(",")
                            cmd = f"input swipe {x1} {y1} {x2} {y2} 300"
                        else:
                            cmd = f"input text '{value}'"
                        result = subprocess.run(
                            [ADB_PATH, "-s", serial, "shell", cmd],
                            capture_output=True, text=True, timeout=10
                        )
                    else:
                        result = subprocess.CompletedProcess([], 1, stdout="", stderr=f"Unknown action: {action}")
                    body = {
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "exit_code": result.returncode
                    }
                    self._send_json_response(200, body, path="/api/adb/exec")
                except Exception as e:
                    self._send_json_response(500, {"error": str(e)}, path="/api/adb/exec")

            elif path == "/api/adb/connect":
                if not self._check_rate_limit():
                    return
                ip_addr = params.get("ip", [""])[0]
                port = params.get("port", ["5555"])[0]
                if not ip_addr:
                    self._send_json_response(400, {"error": "ip required"}, path="/api/adb/connect")
                    return
                try:
                    result = subprocess.run(
                        [ADB_PATH, "connect", f"{ip_addr}:{port}"],
                        capture_output=True, text=True, timeout=10
                    )
                    body = {
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "returncode": result.returncode
                    }
                    self._send_json_response(200, body, path="/api/adb/connect")
                except Exception as e:
                    self._send_json_response(500, {"error": str(e)}, path="/api/adb/connect")

            # ─── Webhook Events (GET = read-only) ────────────────
            elif path == "/api/webhooks/events":
                if not self._check_rate_limit():
                    return
                limit = int(params.get("limit", ["20"])[0])
                try:
                    events = get_recent_events(limit)
                    self._send_json_response(200, {"events": events}, path=path)
                except Exception as e:
                    self._send_json_response(500, {"error": str(e)}, path=path)

            elif path.startswith("/api/webhooks/events/"):
                if not self._check_rate_limit():
                    return
                event_id = path.split("/")[-1]
                try:
                    event = get_event_by_id(event_id)
                    if event:
                        self._send_json_response(200, event, path=path)
                    else:
                        self._send_json_response(404, {"error": "Event not found"}, path=path)
                except Exception as e:
                    self._send_json_response(500, {"error": str(e)}, path=path)

            # ─── Devin AI Endpoints (GET = read-only) ─────────────
            elif path == "/api/devin/status":
                if not self._check_rate_limit():
                    return
                session_id = params.get("session_id", [""])[0]
                if not session_id:
                    # List all sessions
                    try:
                        result = asyncio.run(list_sessions())
                        self._send_json_response(200, {"sessions": result}, path="/api/devin/status")
                    except Exception as e:
                        self._send_json_response(500, {"error": str(e)}, path="/api/devin/status")
                else:
                    # Get specific session
                    try:
                        result = asyncio.run(get_session_status(session_id))
                        if result:
                            self._send_json_response(200, result, path="/api/devin/status")
                        else:
                            self._send_json_response(404, {"error": "Session not found"}, path="/api/devin/status")
                    except Exception as e:
                        self._send_json_response(500, {"error": str(e)}, path="/api/devin/status")

            # ─── Default ───────────────────────────────────────────
            else:
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                apply_cors_headers(self, self.headers.get("Origin"))
                self.end_headers()
                html = (
                    f"<html><body><h1>MiMo Mobile Server</h1>"
                    f"<p>Version: {PROTOCOL_VERSION} | Status: Running</p>"
                    f"<p>WS: {WS_PORT} | HTTP: {HTTP_PORT}</p>"
                    f"<p>Clients: {state.client_count()}</p>"
                    f"<p><a href='/metrics'>Prometheus Metrics</a></p>"
                    f"<p><a href='/api/analytics'>Analytics</a></p>"
                    f"<p><a href='/api/analytics/dau'>Daily Active Users</a></p>"
                    f"<p><a href='/api/analytics/retention'>Retention</a></p>"
                    f"<p><a href='/api/analytics/features'>Feature Usage</a></p>"
                    f"<p>ADB API: /api/adb/devices, /api/adb/exec, /api/adb/connect</p>"
                    f"<p>Devin AI: POST /api/devin/execute, GET /api/devin/status, POST /api/devin/cancel</p>"
                    f"<p>Webhooks: POST /api/webhooks/devin, POST /api/webhooks/github, GET /api/webhooks/events</p>"
                    f"</body></html>"
                )
                self.wfile.write(html.encode())
                HTTP_REQUESTS.labels(path=path, method="GET", status="200").inc()

            elapsed = (time.monotonic() - start) * 1000
            HTTP_REQUEST_DURATION.labels(method="GET", path=path).observe(elapsed / 1000)
            log_request("GET", path, 200, elapsed, ip)

        def do_POST(self):
            start = time.monotonic()
            parsed = urlparse(self.path)
            path = parsed.path
            ip = self._get_client_ip()

            # Read request body
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length > 0 else b''

            try:
                data = json.loads(body) if body else {}
            except json.JSONDecodeError:
                self._send_json_response(400, {"error": "Invalid JSON"}, path=path, method="POST")
                return

            # ─── Devin AI POST Endpoints ─────────────────────────
            if path == "/api/devin/execute":
                if not self._check_rate_limit():
                    return
                task = data.get("task", "")
                branch = data.get("branch", "main")
                description = data.get("description", "")
                if not task:
                    self._send_json_response(400, {"error": "task required in JSON body"}, path=path, method="POST")
                    return
                try:
                    result = asyncio.run(handle_devin_webhook({
                        "action": "execute",
                        "task": task,
                        "params": {"branch": branch, "description": description}
                    }))
                    self._send_json_response(200, result, path=path, method="POST")
                except Exception as e:
                    self._send_json_response(500, {"error": str(e)}, path=path, method="POST")

            elif path == "/api/devin/cancel":
                if not self._check_rate_limit():
                    return
                session_id = data.get("session_id", "")
                if not session_id:
                    self._send_json_response(400, {"error": "session_id required in JSON body"}, path=path, method="POST")
                    return
                try:
                    result = asyncio.run(cancel_session(session_id))
                    self._send_json_response(200, {"cancelled": result}, path=path, method="POST")
                except Exception as e:
                    self._send_json_response(500, {"error": str(e)}, path=path, method="POST")

            # ─── Webhook Receiver Endpoints ──────────────────────
            elif path == "/api/webhooks/devin":
                # Receive webhook from Devin AI
                try:
                    result = asyncio.run(handle_webhook("devin", dict(self.headers), body))
                    self._send_json_response(200, result, path=path, method="POST")
                except Exception as e:
                    self._send_json_response(500, {"error": str(e)}, path=path, method="POST")

            elif path == "/api/webhooks/github":
                # Receive webhook from GitHub
                try:
                    result = asyncio.run(handle_github_webhook(dict(self.headers), body))
                    self._send_json_response(200, result, path=path, method="POST")
                except Exception as e:
                    self._send_json_response(500, {"error": str(e)}, path=path, method="POST")

            elif path.startswith("/api/webhooks/"):
                # Generic webhook receiver
                source = path.split("/")[-1]
                try:
                    result = asyncio.run(handle_webhook(source, dict(self.headers), body))
                    self._send_json_response(200, result, path=path, method="POST")
                except Exception as e:
                    self._send_json_response(500, {"error": str(e)}, path=path, method="POST")

            else:
                self._send_json_response(404, {"error": "Not found"}, path=path, method="POST")

            elapsed = (time.monotonic() - start) * 1000
            HTTP_REQUEST_DURATION.labels(method="POST", path=path).observe(elapsed / 1000)
            log_request("POST", path, 200, elapsed, ip)

        def do_OPTIONS(self):
            self.send_response(200)
            apply_cors_headers(self, self.headers.get("Origin"))
            self.end_headers()

        def log_message(self, format, *args):
            pass

    return HttpRequestHandler


def start_http_server(state):
    try:
        handler = create_http_handler(state)
        server = HTTPServer(("0.0.0.0", HTTP_PORT), handler)
        server.serve_forever()
    except Exception as e:
        print(f"[HTTP] Server error: {e}", flush=True)
