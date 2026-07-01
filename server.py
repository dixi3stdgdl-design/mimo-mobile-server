#!/usr/bin/env python3
"""
MiMo Mobile Server - Pure Python stdlib WebSocket server
Bridges Android app with MiMo Code CLI
"""

import asyncio
import json
import subprocess
import os
import sys
import hashlib
import base64
import struct
import mimetypes
import re
import time
import shutil
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor


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

POWERSHELL = "/mnt/c/WINDOWS/System32/WindowsPowerShell/v1.0/powershell.exe"

def _find_adb():
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
authorized_devices = set()

connected_clients = set()
processes = {}
ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\].*?\x07')
executor = ThreadPoolExecutor(max_workers=4)


def websocket_handshake(key):
    magic = "258EAFA5-E914-47DA-95CA-5AB9A50E6596"
    accept = base64.b64encode(
        hashlib.sha1((key + magic).encode()).digest()
    ).decode()
    return (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept}\r\n"
        "\r\n"
    )


def encode_ws_frame(data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    length = len(data)
    frame = bytearray()
    frame.append(0x81)
    if length < 126:
        frame.append(length)
    elif length < 65536:
        frame.append(126)
        frame.extend(struct.pack(">H", length))
    else:
        frame.append(127)
        frame.extend(struct.pack(">Q", length))
    frame.extend(data)
    return bytes(frame)


def decode_ws_frame(data):
    if len(data) < 2:
        return None, 0
    opcode = data[0] & 0x0F
    masked = data[1] & 0x80
    length = data[1] & 0x7F
    offset = 2
    if length == 126:
        if len(data) < 4:
            return None, 0
        length = struct.unpack(">H", data[2:4])[0]
        offset = 4
    elif length == 127:
        if len(data) < 10:
            return None, 0
        length = struct.unpack(">Q", data[2:10])[0]
        offset = 10
    if masked:
        if len(data) < offset + 4:
            return None, 0
        mask = data[offset:offset + 4]
        offset += 4
    if len(data) < offset + length:
        return None, 0
    payload = bytearray(data[offset:offset + length])
    if masked:
        payload = bytearray(b ^ mask[i % 4] for i, b in enumerate(payload))
    return bytes(payload), offset + length


async def send_json(writer, data):
    try:
        payload = json.dumps(data)
        writer.write(encode_ws_frame(payload))
    except Exception as e:
        print(f"[WS] Send error: {e}", flush=True)


def is_status_line(text):
    if not text:
        return True
    if text.startswith('Available skills:') or text.startswith('compose:'):
        return True
    if not text.strip():
        return True
    return False

# Patterns for terminal output (code, commands, file ops)
TERMINAL_PATTERNS = re.compile(
    r'^(```|import |from |def |class |const |let |var |function |if |for |while |return |'
    r'\$ |# |pip |npm |git |docker |curl |mkdir |chmod |cat |ls |grep |sed |awk |'
    r'await |async |try:|except|raise |print\(|console\.|System\.out)', re.IGNORECASE
)

async def handle_chat(msg, writer):
    prompt = msg.get("prompt", "")
    msg_id = msg.get("id")
    instance_id = msg.get("instance_id", "default")
    
    if instance_id == "default":
        instance_workspace = WORKSPACE
    else:
        instance_workspace = os.path.join(WORKSPACE, f".mimo_instances/{instance_id}")
    os.makedirs(instance_workspace, exist_ok=True)
    
    await send_json(writer, {"type": "chat_start", "id": msg_id, "instance_id": instance_id})

    try:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["TERM"] = "dumb"
        env["PATH"] = os.path.dirname(MIMO_CMD) + ":" + env.get("PATH", "")
        process = await asyncio.create_subprocess_exec(
            MIMO_CMD, "run", prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=instance_workspace,
            env=env
        )
        processes[msg_id] = process

        line_buf = b""
        while True:
            chunk = await asyncio.wait_for(process.stdout.read(4096), timeout=300)
            if not chunk:
                if line_buf:
                    text = ANSI_RE.sub("", line_buf.decode("utf-8", errors="replace")).rstrip()
                    if text and not is_status_line(text):
                        await send_json(writer, {"type": "chat_chunk", "id": msg_id, "instance_id": instance_id, "data": text})
                break
            line_buf += chunk
            while b"\n" in line_buf:
                line, line_buf = line_buf.split(b"\n", 1)
                text = ANSI_RE.sub("", line.decode("utf-8", errors="replace")).rstrip()
                if not text:
                    continue
                if is_status_line(text):
                    continue
                # Route to terminal if it looks like code/output
                if TERMINAL_PATTERNS.match(text):
                    await send_json(writer, {"type": "terminal_chunk", "id": msg_id, "instance_id": instance_id, "data": text})
                else:
                    await send_json(writer, {"type": "chat_chunk", "id": msg_id, "instance_id": instance_id, "data": text})

        await process.wait()
        processes.pop(msg_id, None)
        await send_json(writer, {"type": "chat_end", "id": msg_id, "instance_id": instance_id, "exit_code": process.returncode})
    except FileNotFoundError:
        await send_json(writer, {"type": "chat_end", "id": msg_id, "error": f"Command '{MIMO_CMD}' not found"})
    except asyncio.TimeoutError:
        await send_json(writer, {"type": "chat_end", "id": msg_id, "error": "Response timeout (300s)"})
    except Exception as e:
        await send_json(writer, {"type": "chat_end", "id": msg_id, "error": str(e)})


async def handle_execute(msg, writer):
    command = msg.get("command", "")
    msg_id = msg.get("id")
    instance_id = msg.get("instance_id", "default")
    cwd = msg.get("cwd", os.path.join(WORKSPACE, f".mimo_instances/{instance_id}"))
    os.makedirs(cwd, exist_ok=True)
    await send_json(writer, {"type": "exec_start", "id": msg_id})
    try:
        process = await asyncio.create_subprocess_shell(
            command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, cwd=cwd
        )
        processes[msg_id] = process
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            if text:
                await send_json(writer, {"type": "exec_output", "id": msg_id, "data": text})
        await process.wait()
        processes.pop(msg_id, None)
        await send_json(writer, {"type": "exec_end", "id": msg_id, "exit_code": process.returncode})
    except Exception as e:
        await send_json(writer, {"type": "exec_end", "id": msg_id, "error": str(e)})


async def handle_read_file(msg, writer):
    filepath = msg.get("path", "")
    msg_id = msg.get("id")
    try:
        full_path = os.path.join(WORKSPACE, filepath) if not os.path.isabs(filepath) else filepath
        content = Path(full_path).read_text(encoding="utf-8", errors="replace")
        await send_json(writer, {"type": "file_content", "id": msg_id, "path": filepath, "data": content})
    except Exception as e:
        await send_json(writer, {"type": "error", "id": msg_id, "data": str(e)})


async def handle_write_file(msg, writer):
    filepath = msg.get("path", "")
    content = msg.get("content", "")
    msg_id = msg.get("id")
    try:
        full_path = os.path.join(WORKSPACE, filepath) if not os.path.isabs(filepath) else filepath
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        Path(full_path).write_text(content, encoding="utf-8")
        await send_json(writer, {"type": "file_written", "id": msg_id, "path": filepath})
    except Exception as e:
        await send_json(writer, {"type": "error", "id": msg_id, "data": str(e)})


async def handle_delete_file(msg, writer):
    filepath = msg.get("path", "")
    msg_id = msg.get("id")
    try:
        full_path = os.path.join(WORKSPACE, filepath) if not os.path.isabs(filepath) else filepath
        if os.path.isdir(full_path):
            shutil.rmtree(full_path)
        else:
            os.remove(full_path)
        await send_json(writer, {"type": "file_deleted", "id": msg_id, "path": filepath})
    except Exception as e:
        await send_json(writer, {"type": "error", "id": msg_id, "data": str(e)})


async def handle_list_dir(msg, writer):
    dirpath = msg.get("path", ".")
    msg_id = msg.get("id")
    try:
        full_path = os.path.join(WORKSPACE, dirpath) if not os.path.isabs(dirpath) else dirpath
        entries = []
        for entry in sorted(os.listdir(full_path)):
            full = os.path.join(full_path, entry)
            entries.append({"name": entry, "is_dir": os.path.isdir(full), "size": os.path.getsize(full) if os.path.isfile(full) else 0})
        await send_json(writer, {"type": "dir_listing", "id": msg_id, "path": dirpath, "entries": entries})
    except Exception as e:
        await send_json(writer, {"type": "error", "id": msg_id, "data": str(e)})


async def handle_build_progress(msg, writer):
    msg_id = msg.get("id")
    project_path = msg.get("path", os.path.expanduser("~/ArmandoJauregui"))
    try:
        files = []
        total_size = 0
        kt_count = 0
        xml_count = 0
        gradle_count = 0
        for root, dirs, fnames in os.walk(project_path):
            for fname in fnames:
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, project_path)
                size = os.path.getsize(fpath)
                total_size += size
                ext = os.path.splitext(fname)[1]
                if ext == ".kt": kt_count += 1
                elif ext == ".xml": xml_count += 1
                elif ext in (".kts", ".gradle"): gradle_count += 1
                files.append({"path": rel, "size": size, "ext": ext})
        await send_json(writer, {
            "type": "build_progress",
            "id": msg_id,
            "data": {
                "project": os.path.basename(project_path),
                "total_files": len(files),
                "kt_files": kt_count,
                "xml_files": xml_count,
                "gradle_files": gradle_count,
                "total_size": total_size,
                "files": sorted(files, key=lambda x: x["path"])
            }
        })
    except Exception as e:
        await send_json(writer, {"type": "error", "id": msg_id, "data": str(e)})


async def handle_system_info(msg, writer):
    msg_id = msg.get("id")
    info = {"hostname": os.uname().nodename, "platform": sys.platform, "python": sys.version, "workspace": WORKSPACE, "cwd": os.getcwd()}
    await send_json(writer, {"type": "system_info", "id": msg_id, "data": info})


async def handle_message(message, writer, client_addr=None):
    try:
        msg = json.loads(message)
    except json.JSONDecodeError:
        await send_json(writer, {"type": "error", "data": "Invalid JSON"})
        return
    
    msg_type = msg.get("type")
    msg_id = msg.get("id")
    
    # Authentication check - first message must be auth with correct PIN
    if msg_type == "auth":
        pin = msg.get("pin", "")
        if pin == AUTH_PIN:
            if client_addr:
                authorized_devices.add(client_addr)
            await send_json(writer, {"type": "auth_result", "id": msg_id, "data": "authorized", "status": "ok"})
            print(f"[WS] Device authorized: {client_addr}", flush=True)
        else:
            await send_json(writer, {"type": "auth_result", "id": msg_id, "data": "denied", "status": "error"})
            print(f"[WS] Auth failed: {client_addr}", flush=True)
        return
    
    # All other messages require authorization
    if client_addr and client_addr not in authorized_devices:
        # Allow health check and ping without auth
        if msg_type not in ("ping", "system_info"):
            await send_json(writer, {"type": "error", "id": msg_id, "data": "Not authorized. Send auth message first."})
            return
    
    if msg_type == "chat":
        await handle_chat(msg, writer)
    elif msg_type == "execute":
        await handle_execute(msg, writer)
    elif msg_type == "read_file":
        await handle_read_file(msg, writer)
    elif msg_type == "write_file":
        await handle_write_file(msg, writer)
    elif msg_type == "delete_file":
        await handle_delete_file(msg, writer)
    elif msg_type == "list_dir":
        await handle_list_dir(msg, writer)
    elif msg_type == "ping":
        await send_json(writer, {"type": "pong", "id": msg_id})
    elif msg_type == "build_progress":
        await handle_build_progress(msg, writer)
    elif msg_type == "screen_stream":
        await handle_screen_stream(msg, writer)
    elif msg_type == "continuous_stream":
        await handle_continuous_stream(msg, writer)
    elif msg_type == "mouse_event":
        await handle_mouse_event(msg, writer)
    elif msg_type == "keyboard_event":
        await handle_keyboard_event(msg, writer)
    elif msg_type == "system_info":
        await handle_system_info(msg, writer)
    elif msg_type == "device_list":
        await handle_device_list(msg, writer)
    elif msg_type == "device_command":
        await handle_device_command(msg, writer)
    elif msg_type == "adb_configure":
        await handle_adb_configure(msg, writer)
    else:
        await send_json(writer, {"type": "error", "data": f"Unknown type: {msg_type}"})


active_streams = {}


async def handle_device_list(msg, writer):
    """List all ADB-connected devices"""
    msg_id = msg.get("id")
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
                state = parts[1] if len(parts) > 1 else "unknown"
                model = ""
                for p in parts[2:]:
                    if p.startswith("model:"):
                        model = p.split(":")[1]
                devices.append({"serial": serial, "state": state, "model": model})
        await send_json(writer, {"type": "device_list", "id": msg_id, "data": devices})
    except Exception as e:
        await send_json(writer, {"type": "error", "id": msg_id, "data": str(e)})


async def handle_device_command(msg, writer):
    """Execute ADB command on a specific device"""
    msg_id = msg.get("id")
    serial = msg.get("serial", "")
    command = msg.get("command", "")
    action = msg.get("action", "shell")

    try:
        if action == "shell":
            result = subprocess.run(
                [ADB_PATH, "-s", serial, "shell", command],
                capture_output=True, text=True, timeout=30
            )
            await send_json(writer, {
                "type": "device_output", "id": msg_id, "serial": serial,
                "stdout": result.stdout, "stderr": result.stderr,
                "exit_code": result.returncode
            })
        elif action == "install":
            apk_path = msg.get("apk_path", "")
            result = subprocess.run(
                [ADB_PATH, "-s", serial, "install", "-r", apk_path],
                capture_output=True, text=True, timeout=120
            )
            await send_json(writer, {
                "type": "device_output", "id": msg_id, "serial": serial,
                "stdout": result.stdout, "stderr": result.stderr,
                "exit_code": result.returncode
            })
        elif action == "launch":
            component = msg.get("component", "")
            result = subprocess.run(
                [ADB_PATH, "-s", serial, "shell", "am", "start", "-n", component],
                capture_output=True, text=True, timeout=10
            )
            await send_json(writer, {
                "type": "device_output", "id": msg_id, "serial": serial,
                "stdout": result.stdout, "exit_code": result.returncode
            })
        elif action == "input":
            input_type = msg.get("input_type", "text")
            value = msg.get("value", "")
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
            await send_json(writer, {
                "type": "device_output", "id": msg_id, "serial": serial,
                "stdout": result.stdout, "exit_code": result.returncode
            })
        elif action == "screenshot":
            result = subprocess.run(
                [ADB_PATH, "-s", serial, "shell", "screencap", "-p", "/sdcard/mimo_screenshot.png"],
                capture_output=True, text=True, timeout=10
            )
            pull = subprocess.run(
                [ADB_PATH, "-s", serial, "pull", "/sdcard/mimo_screenshot.png", f"/tmp/mimo_{serial}.png"],
                capture_output=True, text=True, timeout=10
            )
            await send_json(writer, {
                "type": "device_output", "id": msg_id, "serial": serial,
                "stdout": "Screenshot saved", "exit_code": 0
            })
        elif action == "settings":
            setting_type = msg.get("setting_type", "system")
            key = msg.get("key", "")
            value = msg.get("value", "")
            result = subprocess.run(
                [ADB_PATH, "-s", serial, "shell", "settings", "put", setting_type, key, value],
                capture_output=True, text=True, timeout=10
            )
            await send_json(writer, {
                "type": "device_output", "id": msg_id, "serial": serial,
                "stdout": result.stdout, "exit_code": result.returncode
            })
    except Exception as e:
        await send_json(writer, {"type": "error", "id": msg_id, "data": str(e)})


async def handle_adb_configure(msg, writer):
    """Auto-configure ADB wireless debugging on a device"""
    msg_id = msg.get("id")
    serial = msg.get("serial", "")
    try:
        # Enable TCP/IP mode
        subprocess.run(
            [ADB_PATH, "-s", serial, "tcpip", "5555"],
            capture_output=True, text=True, timeout=10
        )
        await asyncio.sleep(2)

        # Get device WiFi IP
        result = subprocess.run(
            [ADB_PATH, "-s", serial, "shell", "ip", "addr", "show", "wlan0"],
            capture_output=True, text=True, timeout=10
        )
        ip = ""
        for line in result.stdout.split("\n"):
            if "inet " in line:
                ip = line.strip().split("inet ")[1].split("/")[0]
                break

        if ip:
            # Connect wirelessly
            connect_result = subprocess.run(
                [ADB_PATH, "connect", f"{ip}:5555"],
                capture_output=True, text=True, timeout=10
            )
            await send_json(writer, {
                "type": "adb_configured", "id": msg_id, "serial": serial,
                "ip": ip, "wireless": True,
                "stdout": connect_result.stdout
            })
        else:
            await send_json(writer, {
                "type": "adb_configured", "id": msg_id, "serial": serial,
                "wireless": False, "error": "Could not determine WiFi IP"
            })
    except Exception as e:
        await send_json(writer, {"type": "error", "id": msg_id, "data": str(e)})


async def handle_continuous_stream(msg, writer):
    action = msg.get("action", "start")
    msg_id = msg.get("id")
    if action == "start":
        streaming = {"active": True, "writer": writer, "thread": None}
        loop = asyncio.get_event_loop()
        
        def stream_loop():
            while streaming["active"]:
                try:
                    result = subprocess.run(
                        [POWERSHELL, "-Command",
                         "Add-Type -AssemblyName System.Windows.Forms; "
                         "$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds; "
                         "$bmp = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height); "
                         "$gfx = [System.Drawing.Graphics]::FromImage($bmp); "
                         "$gfx.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size); "
                         "$ms = New-Object System.IO.MemoryStream; "
                         "$bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Jpeg); "
                         "[Convert]::ToBase64String($ms.ToArray())"],
                        capture_output=True, text=True, timeout=10
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        b64 = result.stdout.strip()
                        asyncio.run_coroutine_threadsafe(
                            send_json(streaming["writer"], {
                                "type": "screen_frame",
                                "id": msg_id,
                                "data": b64,
                                "format": "jpeg"
                            }),
                            loop
                        )
                except Exception as e:
                    print(f"Stream error: {e}", flush=True)
                time.sleep(0.1)
        
        import threading
        streaming["thread"] = threading.Thread(target=stream_loop, daemon=True)
        streaming["thread"].start()
        active_streams[msg_id] = streaming
        await send_json(writer, {"type": "stream_status", "id": msg_id, "data": "started"})
    elif action == "stop":
        if msg_id in active_streams:
            active_streams[msg_id]["active"] = False
            del active_streams[msg_id]
        await send_json(writer, {"type": "stream_status", "id": msg_id, "data": "stopped"})


async def handle_screen_stream(msg, writer):
    msg_id = msg.get("id")
    action = msg.get("action", "capture")
    if action == "capture":
        try:
            import subprocess
            result = subprocess.run(
                [POWERSHELL, "-Command",
                 "Add-Type -AssemblyName System.Windows.Forms; "
                 "$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds; "
                 "$bmp = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height); "
                 "$gfx = [System.Drawing.Graphics]::FromImage($bmp); "
                 "$gfx.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size); "
                 "$ms = New-Object System.IO.MemoryStream; "
                 "$bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Jpeg); "
                 "[Convert]::ToBase64String($ms.ToArray())"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                b64 = result.stdout.strip()
                await send_json(writer, {
                    "type": "screen_frame",
                    "id": msg_id,
                    "data": b64,
                    "format": "jpeg"
                })
            else:
                await send_json(writer, {"type": "screen_frame", "id": msg_id, "error": "Capture failed"})
        except Exception as e:
            await send_json(writer, {"type": "screen_frame", "id": msg_id, "error": str(e)})
    elif action == "start_stream":
        await send_json(writer, {"type": "screen_stream_status", "id": msg_id, "data": "started"})
    elif action == "stop_stream":
        await send_json(writer, {"type": "screen_stream_status", "id": msg_id, "data": "stopped"})


async def handle_mouse_event(msg, writer):
    msg_id = msg.get("id")
    x = msg.get("x", 0)
    y = msg.get("y", 0)
    action = msg.get("action", "click")
    button = msg.get("button", "left")
    try:
        import subprocess
        if action == "click":
            btn = "1" if button == "left" else "2" if button == "right" else "3"
            subprocess.run(
                [POWERSHELL, "-Command",
                 f"Add-Type -AssemblyName System.Windows.Forms; "
                 f"[System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point({x}, {y}); "
                 f"$sig = '[user32.dll]mouse_event'; "
                 f"Add-Type -MemberDefinition $sig -Name U -Namespace W; "
                 f"[W.U]::mouse_event({btn}, 0, 0, 0, 0)"],
                capture_output=True, timeout=5
            )
        elif action == "move":
            subprocess.run(
                [POWERSHELL, "-Command",
                 f"Add-Type -AssemblyName System.Windows.Forms; "
                 f"[System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point({x}, {y})"],
                capture_output=True, timeout=5
            )
        elif action == "scroll":
            delta = msg.get("delta", 120)
            subprocess.run(
                [POWERSHELL, "-Command",
                 f"Add-Type -AssemblyName System.Windows.Forms; "
                 f"[System.Windows.Forms.Cursor]::Position = New-Object System.Drawing.Point({x}, {y}); "
                 f"$sig = '[user32.dll]mouse_event'; "
                 f"Add-Type -MemberDefinition $sig -Name U -Namespace W; "
                 f"[W.U]::mouse_event(2048, 0, 0, {delta}, 0)"],
                capture_output=True, timeout=5
            )
        await send_json(writer, {"type": "mouse_ack", "id": msg_id, "data": "ok"})
    except Exception as e:
        await send_json(writer, {"type": "error", "id": msg_id, "data": str(e)})


async def handle_keyboard_event(msg, writer):
    msg_id = msg.get("id")
    key = msg.get("key", "")
    action = msg.get("action", "press")
    try:
        import subprocess
        if action == "type":
            escaped = key.replace("'", "''")
            subprocess.run(
                [POWERSHELL, "-Command",
                 f"Add-Type -AssemblyName System.Windows.Forms; "
                 f"[System.Windows.Forms.SendKeys]::SendWait('{escaped}')"],
                capture_output=True, timeout=5
            )
        elif action == "hotkey":
            keys = key.split("+")
            combo = "{".join(keys) + "}"
            subprocess.run(
                [POWERSHELL, "-Command",
                 f"Add-Type -AssemblyName System.Windows.Forms; "
                 f"[System.Windows.Forms.SendKeys]::SendWait('{combo}')"],
                capture_output=True, timeout=5
            )
        await send_json(writer, {"type": "keyboard_ack", "id": msg_id, "data": "ok"})
    except Exception as e:
        await send_json(writer, {"type": "error", "id": msg_id, "data": str(e)})


class WebSocketProtocol(asyncio.Protocol):
    def connection_made(self, transport):
        self.transport = transport
        self.buf = b""
        self.handshake_done = False
        self.addr = transport.get_extra_info("peername")
        self.http_buf = b""
        self.last_pong = time.time()
        self.last_activity = time.time()
        print(f"[WS] Connection from {self.addr}", flush=True)

    def data_received(self, data):
        self.buf += data
        self.last_activity = time.time()
        if not self.handshake_done:
            idx = self.buf.find(b"\r\n\r\n")
            if idx == -1:
                return
            header = self.buf[:idx].decode("utf-8", errors="replace")
            self.buf = self.buf[idx + 4:]
            print(f"[WS] Handshake header: {header[:200]}", flush=True)
            if "Upgrade: websocket" not in header and "Upgrade: WebSocket" not in header:
                self.transport.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                self.transport.close()
                return
            ws_key = None
            for line in header.split("\r\n"):
                if line.lower().startswith("sec-websocket-key:"):
                    ws_key = line.split(":", 1)[1].strip()
                    break
            if not ws_key:
                self.transport.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                self.transport.close()
                return
            print(f"[WS] Handshake key: {ws_key[:20]}...", flush=True)
            self.transport.write(websocket_handshake(ws_key).encode())
            self.handshake_done = True
            connected_clients.add(self)
            print(f"[WS] Client connected: {self.addr}", flush=True)
            if self.buf:
                self._process_frames()
        else:
            self._process_frames()

    def _process_frames(self):
        while len(self.buf) >= 2:
            b1 = self.buf[0] & 0xFF
            b2 = self.buf[1] & 0xFF
            opcode = b1 & 0x0F
            if opcode not in (0, 1, 2, 8, 9, 10):
                self.buf = self.buf[1:]
                continue
            if opcode == 0x08:
                self.buf = self.buf[2:]
                self.close()
                return
            if opcode == 0x09:
                self.buf = self.buf[2:]
                pong_frame = bytearray([0x8A, 0x00])
                try:
                    self.transport.write(bytes(pong_frame))
                except Exception:
                    pass
                continue
            if opcode == 0x0A:
                self.buf = self.buf[2:]
                self.last_pong = time.time()
                continue
            length = self.buf[1] & 0x7F
            masked = self.buf[1] & 0x80
            offset = 2
            if length == 126:
                if len(self.buf) < 4: return
                length = struct.unpack(">H", self.buf[2:4])[0]
                offset = 4
            elif length == 127:
                if len(self.buf) < 10: return
                length = struct.unpack(">Q", self.buf[2:10])[0]
                offset = 10
            if masked:
                if len(self.buf) < offset + 4: return
                mask = self.buf[offset:offset + 4]
                offset += 4
            if len(self.buf) < offset + length:
                return
            payload = bytearray(self.buf[offset:offset + length])
            if masked:
                payload = bytearray(b ^ mask[i % 4] for i, b in enumerate(payload))
            self.buf = self.buf[offset + length:]
            if payload:
                msg_text = bytes(payload).decode("utf-8", errors="replace")
                print(f"[WS] Received from {self.addr}: {msg_text[:150]}", flush=True)
                asyncio.ensure_future(self._handle(msg_text))

    async def _handle(self, msg_text):
        try:
            await handle_message(msg_text, self, self.addr)
        except Exception as e:
            print(f"[WS] Handle error: {e}", flush=True)

    def write(self, data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        try:
            self.transport.write(data)
        except Exception:
            pass

    def close(self):
        try:
            self.transport.close()
        except Exception:
            pass

    def connection_lost(self, exc):
        connected_clients.discard(self)
        if self.addr in authorized_devices:
            authorized_devices.discard(self.addr)
        print(f"[WS] Client disconnected: {self.addr}", flush=True)


class HttpRequestHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            response = json.dumps({"status": "ok", "ws_port": WS_PORT, "workspace": WORKSPACE, "clients": len(connected_clients), "name": MIMO_SERVER_NAME})
            self.wfile.write(response.encode())
        elif parsed.path == "/api/exec":
            params = parse_qs(parsed.query)
            cmd = params.get("command", [""])[0]
            try:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30, cwd=WORKSPACE)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode}).encode())
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            html = f"<html><body><h1>MiMo Mobile Server</h1><p>Running</p><p>WS: {WS_PORT} | HTTP: {HTTP_PORT}</p><p>Clients: {len(connected_clients)}</p></body></html>"
            self.wfile.write(html.encode())

    def log_message(self, format, *args):
        pass


def http_server():
    try:
        server = HTTPServer((HOST, HTTP_PORT), HttpRequestHandler)
        server.serve_forever()
    except Exception as e:
        print(f"[HTTP] Server error: {e}", flush=True)


async def heartbeat():
    while True:
        await asyncio.sleep(30)
        now = time.time()
        dead = []
        for client in list(connected_clients):
            if not client.handshake_done:
                continue
            if now - client.last_activity > 120:
                dead.append(client)
                continue
            try:
                ping_frame = bytearray([0x89, 0x00])
                client.transport.write(bytes(ping_frame))
            except Exception:
                dead.append(client)
        for client in dead:
            print(f"[WS] Heartbeat timeout: {client.addr}", flush=True)
            client.close()
        alive = len(connected_clients) - len(dead)
        if alive > 0 or len(dead) > 0:
            print(f"[WS] Heartbeat: {alive} alive, {len(dead)} removed", flush=True)


def main():
    print("=" * 50, flush=True)
    print("  MiMo Mobile Server", flush=True)
    print(f"  Workspace: {WORKSPACE}", flush=True)
    print(f"  WebSocket: ws://0.0.0.0:{WS_PORT}", flush=True)
    print(f"  HTTP:      http://0.0.0.0:{HTTP_PORT}", flush=True)
    print("=" * 50, flush=True)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    http_thread = __import__("threading").Thread(target=http_server, daemon=True)
    http_thread.start()

    server = loop.run_until_complete(
        loop.create_server(WebSocketProtocol, HOST, WS_PORT)
    )
    print(f"[WS] WebSocket server running on ws://{HOST}:{WS_PORT}", flush=True)

    loop.create_task(heartbeat())
    print("[WS] Heartbeat started (30s interval)", flush=True)

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()


if __name__ == "__main__":
    main()
