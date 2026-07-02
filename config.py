"""Environment configuration and constants."""

import os
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

HOST = "0.0.0.0"
WS_PORT = int(os.environ.get("MIMO_WS_PORT", "8765"))
HTTP_PORT = int(os.environ.get("MIMO_HTTP_PORT", "8080"))
WORKSPACE = os.environ.get("MIMO_WORKSPACE", os.path.expanduser("~"))
MIMO_CMD = os.environ.get("MIMO_CMD", os.path.expanduser("~/.mimocode/bin/mimo"))
MIMO_SERVER_NAME = os.environ.get("MIMO_SERVER_NAME", os.uname().nodename)
REDIS_URL = os.environ.get("REDIS_URL", "")
WORKERS = int(os.environ.get("MIMO_WORKERS", "1"))

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
AUTH_PIN = os.environ.get("MIMO_AUTH_PIN", "MIMO2026")
