"""File operation handlers — read, write, delete, list."""

import os
import shutil
from pathlib import Path

from protocol import send_json
from config import WORKSPACE


async def handle_read_file(msg, writer, state=None):
    filepath = msg.get("path", "")
    msg_id = msg.get("id")
    try:
        full_path = os.path.join(WORKSPACE, filepath) if not os.path.isabs(filepath) else filepath
        content = Path(full_path).read_text(encoding="utf-8", errors="replace")
        await send_json(writer, {"type": "file_content", "id": msg_id, "path": filepath, "data": content})
    except Exception as e:
        await send_json(writer, {"type": "error", "id": msg_id, "data": str(e)})


async def handle_write_file(msg, writer, state=None):
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


async def handle_delete_file(msg, writer, state=None):
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


async def handle_list_dir(msg, writer, state=None):
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
