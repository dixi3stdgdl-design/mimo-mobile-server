"""Chat handler — runs mimo CLI and streams output."""

import asyncio
import os
import re

from protocol import send_json
from config import WORKSPACE, MIMO_CMD
from metrics import CHAT_COMMANDS

ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]|\x1b\].*?\x07')

TERMINAL_PATTERNS = re.compile(
    r'^(```|import |from |def |class |const |let |var |function |if |for |while |return |'
    r'\$ |# |pip |npm |git |docker |curl |mkdir |chmod |cat |ls |grep |sed |awk |'
    r'await |async |try:|except|raise |print\(|console\.|System\.out)', re.IGNORECASE
)


def is_status_line(text):
    if not text:
        return True
    if text.startswith('Available skills:') or text.startswith('compose:'):
        return True
    if not text.strip():
        return True
    return False


async def handle_chat(msg, writer, state=None):
    prompt = msg.get("prompt", "")
    msg_id = msg.get("id")
    instance_id = msg.get("instance_id", "default")

    if instance_id == "default":
        instance_workspace = WORKSPACE
    else:
        instance_workspace = os.path.join(WORKSPACE, f".mimo_instances/{instance_id}")
    os.makedirs(instance_workspace, exist_ok=True)

    await send_json(writer, {"type": "chat_start", "id": msg_id, "instance_id": instance_id})
    CHAT_COMMANDS.inc()

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
        if state:
            state.register_process(msg_id, process)

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
                if TERMINAL_PATTERNS.match(text):
                    await send_json(writer, {"type": "terminal_chunk", "id": msg_id, "instance_id": instance_id, "data": text})
                else:
                    await send_json(writer, {"type": "chat_chunk", "id": msg_id, "instance_id": instance_id, "data": text})

        await process.wait()
        if state:
            state.unregister_process(msg_id)
        await send_json(writer, {"type": "chat_end", "id": msg_id, "instance_id": instance_id, "exit_code": process.returncode})
    except FileNotFoundError:
        await send_json(writer, {"type": "chat_end", "id": msg_id, "error": f"Command '{MIMO_CMD}' not found"})
    except asyncio.TimeoutError:
        await send_json(writer, {"type": "chat_end", "id": msg_id, "error": "Response timeout (300s)"})
    except Exception as e:
        await send_json(writer, {"type": "chat_end", "id": msg_id, "error": str(e)})
