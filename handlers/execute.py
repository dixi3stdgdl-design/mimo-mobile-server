"""Execute handler — runs shell commands."""

import asyncio
import os

from protocol import send_json
from config import WORKSPACE


async def handle_execute(msg, writer, state=None):
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
        if state:
            state.register_process(msg_id, process)
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            if text:
                await send_json(writer, {"type": "exec_output", "id": msg_id, "data": text})
        await process.wait()
        if state:
            state.unregister_process(msg_id)
        await send_json(writer, {"type": "exec_end", "id": msg_id, "exit_code": process.returncode})
    except Exception as e:
        await send_json(writer, {"type": "exec_end", "id": msg_id, "error": str(e)})
