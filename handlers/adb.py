"""ADB device management handlers."""

import asyncio
import subprocess

from protocol import send_json
from config import ADB_PATH


async def handle_device_list(msg, writer, state=None):
    msg_id = msg.get("id")
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: subprocess.run(
            [ADB_PATH, "devices", "-l"],
            capture_output=True, text=True, timeout=10
        ))
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
        await send_json(writer, {"type": "device_list", "id": msg_id, "data": devices})
    except Exception as e:
        await send_json(writer, {"type": "error", "id": msg_id, "data": str(e)})


async def handle_device_command(msg, writer, state=None):
    msg_id = msg.get("id")
    serial = msg.get("serial", "")
    command = msg.get("command", "")
    action = msg.get("action", "shell")

    try:
        loop = asyncio.get_event_loop()

        if action == "shell":
            result = await loop.run_in_executor(None, lambda: subprocess.run(
                [ADB_PATH, "-s", serial, "shell", command],
                capture_output=True, text=True, timeout=30
            ))
            await send_json(writer, {
                "type": "device_output", "id": msg_id, "serial": serial,
                "stdout": result.stdout, "stderr": result.stderr,
                "exit_code": result.returncode
            })
        elif action == "install":
            apk_path = msg.get("apk_path", "")
            result = await loop.run_in_executor(None, lambda: subprocess.run(
                [ADB_PATH, "-s", serial, "install", "-r", apk_path],
                capture_output=True, text=True, timeout=120
            ))
            await send_json(writer, {
                "type": "device_output", "id": msg_id, "serial": serial,
                "stdout": result.stdout, "stderr": result.stderr,
                "exit_code": result.returncode
            })
        elif action == "launch":
            component = msg.get("component", "")
            result = await loop.run_in_executor(None, lambda: subprocess.run(
                [ADB_PATH, "-s", serial, "shell", "am", "start", "-n", component],
                capture_output=True, text=True, timeout=10
            ))
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
            result = await loop.run_in_executor(None, lambda: subprocess.run(
                [ADB_PATH, "-s", serial, "shell", cmd],
                capture_output=True, text=True, timeout=10
            ))
            await send_json(writer, {
                "type": "device_output", "id": msg_id, "serial": serial,
                "stdout": result.stdout, "exit_code": result.returncode
            })
        elif action == "screenshot":
            await loop.run_in_executor(None, lambda: subprocess.run(
                [ADB_PATH, "-s", serial, "shell", "screencap", "-p", "/sdcard/mimo_screenshot.png"],
                capture_output=True, text=True, timeout=10
            ))
            await loop.run_in_executor(None, lambda: subprocess.run(
                [ADB_PATH, "-s", serial, "pull", "/sdcard/mimo_screenshot.png", f"/tmp/mimo_{serial}.png"],
                capture_output=True, text=True, timeout=10
            ))
            await send_json(writer, {
                "type": "device_output", "id": msg_id, "serial": serial,
                "stdout": "Screenshot saved", "exit_code": 0
            })
        elif action == "settings":
            setting_type = msg.get("setting_type", "system")
            key = msg.get("key", "")
            value = msg.get("value", "")
            result = await loop.run_in_executor(None, lambda: subprocess.run(
                [ADB_PATH, "-s", serial, "shell", "settings", "put", setting_type, key, value],
                capture_output=True, text=True, timeout=10
            ))
            await send_json(writer, {
                "type": "device_output", "id": msg_id, "serial": serial,
                "stdout": result.stdout, "exit_code": result.returncode
            })
    except Exception as e:
        await send_json(writer, {"type": "error", "id": msg_id, "data": str(e)})


async def handle_adb_configure(msg, writer, state=None):
    msg_id = msg.get("id")
    serial = msg.get("serial", "")
    try:
        loop = asyncio.get_event_loop()

        await loop.run_in_executor(None, lambda: subprocess.run(
            [ADB_PATH, "-s", serial, "tcpip", "5555"],
            capture_output=True, text=True, timeout=10
        ))
        await asyncio.sleep(2)

        result = await loop.run_in_executor(None, lambda: subprocess.run(
            [ADB_PATH, "-s", serial, "shell", "ip", "addr", "show", "wlan0"],
            capture_output=True, text=True, timeout=10
        ))
        ip = ""
        for line in result.stdout.split("\n"):
            if "inet " in line:
                ip = line.strip().split("inet ")[1].split("/")[0]
                break

        if ip:
            connect_result = await loop.run_in_executor(None, lambda: subprocess.run(
                [ADB_PATH, "connect", f"{ip}:5555"],
                capture_output=True, text=True, timeout=10
            ))
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
