"""HTTP request handler with metrics and health endpoints."""

import json
import subprocess
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from config import WS_PORT, HTTP_PORT, WORKSPACE, MIMO_SERVER_NAME
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
                    f"</body></html>"
                )
                self.wfile.write(html.encode())

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
