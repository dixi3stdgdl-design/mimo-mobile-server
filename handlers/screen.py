"""Screen capture and remote input handlers."""

import asyncio
import time
import threading
import subprocess

from protocol import send_json
from config import POWERSHELL
from metrics import SCREEN_FRAMES


async def handle_screen_stream(msg, writer, state=None):
    msg_id = msg.get("id")
    action = msg.get("action", "capture")
    if action == "capture":
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
            SCREEN_FRAMES.inc()
            if result.returncode == 0 and result.stdout.strip():
                b64 = result.stdout.strip()
                await send_json(writer, {"type": "screen_frame", "id": msg_id, "data": b64, "format": "jpeg"})
            else:
                await send_json(writer, {"type": "screen_frame", "id": msg_id, "error": "Capture failed"})
        except Exception as e:
            await send_json(writer, {"type": "screen_frame", "id": msg_id, "error": str(e)})
    elif action == "start_stream":
        await send_json(writer, {"type": "screen_stream_status", "id": msg_id, "data": "started"})
    elif action == "stop_stream":
        await send_json(writer, {"type": "screen_stream_status", "id": msg_id, "data": "stopped"})


async def handle_continuous_stream(msg, writer, state=None):
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
                    SCREEN_FRAMES.inc()
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

        streaming["thread"] = threading.Thread(target=stream_loop, daemon=True)
        streaming["thread"].start()
        if state:
            state.register_stream(msg_id, streaming)
        await send_json(writer, {"type": "stream_status", "id": msg_id, "data": "started"})
    elif action == "stop":
        if state:
            state.stop_stream(msg_id)
        await send_json(writer, {"type": "stream_status", "id": msg_id, "data": "stopped"})


async def handle_mouse_event(msg, writer, state=None):
    msg_id = msg.get("id")
    x = msg.get("x", 0)
    y = msg.get("y", 0)
    action = msg.get("action", "click")
    button = msg.get("button", "left")
    try:
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


async def handle_keyboard_event(msg, writer, state=None):
    msg_id = msg.get("id")
    key = msg.get("key", "")
    action = msg.get("action", "press")
    try:
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
