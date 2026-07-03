"""HTTP request handler with metrics, health, and ADB endpoints."""

import json
import subprocess
import asyncio
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from config import WS_PORT, HTTP_PORT, WORKSPACE, MIMO_SERVER_NAME, ADB_PATH
from metrics import HTTP_REQUESTS, get_metrics, METRICS_CONTENT_TYPE


def create_http_handler(state):
    """Create HttpRequestHandler with bound state."""

    class HttpRequestHandler(SimpleHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path

            if path == "/health":
                HTTP_REQUESTS.labels(path="/health", method="GET", status="200").inc()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                response = json.dumps({
                    "status": "ok",
                    "ws_port": WS_PORT,
                    "workspace": WORKSPACE,
                    "clients": state.client_count(),
                    "name": MIMO_SERVER_NAME
                })
                self.wfile.write(response.encode())

            elif path == "/metrics":
                HTTP_REQUESTS.labels(path="/metrics", method="GET", status="200").inc()
                self.send_response(200)
                self.send_header("Content-Type", METRICS_CONTENT_TYPE)
                self.end_headers()
                self.wfile.write(get_metrics())

            elif path == "/api/exec":
                HTTP_REQUESTS.labels(path="/api/exec", method="GET", status="200").inc()
                params = parse_qs(parsed.query)
                cmd = params.get("command", [""])[0]
                try:
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30, cwd=WORKSPACE)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "returncode": result.returncode
                    }).encode())
                except Exception as e:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode())

            elif path == "/api/adb/devices":
                HTTP_REQUESTS.labels(path="/api/adb/devices", method="GET", status="200").inc()
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
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps({"devices": devices}).encode())
                except Exception as e:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode())

            elif path == "/api/adb/exec":
                HTTP_REQUESTS.labels(path="/api/adb/exec", method="GET", status="200").inc()
                params = parse_qs(parsed.query)
                serial = params.get("serial", [""])[0]
                command = params.get("command", [""])[0]
                action = params.get("action", ["shell"])[0]
                if not serial or not command:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "serial and command required"}).encode())
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
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "exit_code": result.returncode
                    }).encode())
                except Exception as e:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode())

            elif path == "/api/adb/connect":
                HTTP_REQUESTS.labels(path="/api/adb/connect", method="GET", status="200").inc()
                params = parse_qs(parsed.query)
                ip = params.get("ip", [""])[0]
                port = params.get("port", ["5555"])[0]
                if not ip:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "ip required"}).encode())
                    return
                try:
                    result = subprocess.run(
                        [ADB_PATH, "connect", f"{ip}:{port}"],
                        capture_output=True, text=True, timeout=10
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "returncode": result.returncode
                    }).encode())
                except Exception as e:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode())

            else:
                HTTP_REQUESTS.labels(path=path, method="GET", status="200").inc()
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                html = (
                    f"<html><body><h1>MiMo Mobile Server</h1>"
                    f"<p>Running</p>"
                    f"<p>WS: {WS_PORT} | HTTP: {HTTP_PORT}</p>"
                    f"<p>Clients: {state.client_count()}</p>"
                    f"<p><a href='/metrics'>Metrics</a></p>"
                    f"<p>ADB API: /api/adb/devices, /api/adb/exec, /api/adb/connect</p>"
                    f"</body></html>"
                )
                self.wfile.write(html.encode())

        def do_OPTIONS(self):
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
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
