"""System info and build progress handlers."""

import os
import sys

from protocol import send_json
from config import WORKSPACE


async def handle_build_progress(msg, writer, state=None):
    msg_id = msg.get("id")
    project_path = msg.get("path", WORKSPACE)
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
                if ext == ".kt":
                    kt_count += 1
                elif ext == ".xml":
                    xml_count += 1
                elif ext in (".kts", ".gradle"):
                    gradle_count += 1
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


async def handle_system_info(msg, writer, state=None):
    msg_id = msg.get("id")
    info = {
        "hostname": os.uname().nodename,
        "platform": sys.platform,
        "python": sys.version,
        "workspace": WORKSPACE,
        "cwd": os.getcwd()
    }
    await send_json(writer, {"type": "system_info", "id": msg_id, "data": info})
