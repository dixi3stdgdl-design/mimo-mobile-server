"""Environment configuration and constants."""

import os
import secrets
from pathlib import Path


def load_env():
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value


load_env()

# ─── Server Config ────────────────────────────────────────────────────
HOST = "0.0.0.0"
WS_PORT = int(os.environ.get("MIMO_WS_PORT", "8765"))
HTTP_PORT = int(os.environ.get("MIMO_HTTP_PORT", "8080"))
WORKSPACE = os.environ.get("MIMO_WORKSPACE", os.path.expanduser("~"))
MIMO_CMD = os.environ.get("MIMO_CMD", "/usr/local/bin/mimo")
MIMO_SERVER_NAME = os.environ.get("MIMO_SERVER_NAME", os.uname().nodename)
REDIS_URL = os.environ.get("REDIS_URL", "")
WORKERS = int(os.environ.get("MIMO_WORKERS", "1"))

# ─── Auth Config ──────────────────────────────────────────────────────
AUTH_PIN = os.environ.get("MIMO_AUTH_PIN", "MIMO2026")
JWT_SECRET = os.environ.get("MIMO_JWT_SECRET", "")
JWT_EXPIRY = int(os.environ.get("MIMO_JWT_EXPIRY", "86400"))  # 24 hours
API_KEYS = os.environ.get("MIMO_API_KEYS", "")  # Format: key1:user1,key2:user2


def validate_env():
    """Validate required environment variables on startup. Fail fast if missing."""
    errors = []

    jwt_secret = os.environ.get("MIMO_JWT_SECRET", "")
    ws_port = int(os.environ.get("MIMO_WS_PORT", "8765"))
    http_port = int(os.environ.get("MIMO_HTTP_PORT", "8080"))

    if not jwt_secret:
        errors.append("MIMO_JWT_SECRET is required but not set. Generate one with: python -c 'import secrets; print(secrets.token_hex(32))'")

    if ws_port < 1 or ws_port > 65535:
        errors.append(f"MIMO_WS_PORT must be 1-65535, got {ws_port}")

    if http_port < 1 or http_port > 65535:
        errors.append(f"MIMO_HTTP_PORT must be 1-65535, got {http_port}")

    if ws_port == http_port:
        errors.append(f"MIMO_WS_PORT and MIMO_HTTP_PORT must be different (both {ws_port})")

    if errors:
        print("=" * 60, flush=True)
        print("  FATAL: Environment validation failed", flush=True)
        print("=" * 60, flush=True)
        for err in errors:
            print(f"  - {err}", flush=True)
        print("=" * 60, flush=True)
        import sys
        sys.exit(1)

# ─── TLS Config ───────────────────────────────────────────────────────
TLS_ENABLED = os.environ.get("MIMO_TLS_ENABLED", "false").lower() == "true"
TLS_CERT_DIR = os.environ.get("MIMO_TLS_CERT_DIR", "./certs")

# ─── Cloudflare Tunnel ────────────────────────────────────────────────
CLOUDFLARE_TUNNEL = os.environ.get("MIMO_CLOUDFLARE_TUNNEL", "false").lower() == "true"
CLOUDFLARE_TUNNEL_TOKEN = os.environ.get("CLOUDFLARE_TUNNEL_TOKEN", "")
EXTERNAL_HOST = os.environ.get("MIMO_EXTERNAL_HOST", "")

# ─── Analytics Config ─────────────────────────────────────────────────
ANALYTICS_ENABLED = os.environ.get("MIMO_ANALYTICS_ENABLED", "true").lower() == "true"
ANALYTICS_DB = os.environ.get("MIMO_ANALYTICS_DB", os.path.expanduser("~/.mimo/analytics.db"))

# ─── Protocol Config ──────────────────────────────────────────────────
PROTOCOL_VERSION = "1.0"
PROTOCOL_NAME = "mimocode"

POWERSHELL = "/mnt/c/WINDOWS/System32/WindowsPowerShell/v1.0/powershell.exe"


def _find_adb():
    import shutil
    env_adb = os.environ.get("ANDROID_HOME", "")
    if env_adb:
        p = os.path.join(env_adb, "platform-tools", "adb")
        if os.path.isfile(p):
            return p
    found = shutil.which("adb")
    if found:
        return found
    return "/home/DexTer/Android/Sdk/platform-tools/adb"


ADB_PATH = _find_adb()
