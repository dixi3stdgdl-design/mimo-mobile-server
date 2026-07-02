"""Handler registry for WebSocket message dispatch."""

from .chat import handle_chat
from .execute import handle_execute
from .files import handle_read_file, handle_write_file, handle_delete_file, handle_list_dir
from .screen import handle_screen_stream, handle_continuous_stream, handle_mouse_event, handle_keyboard_event
from .adb import handle_device_list, handle_device_command, handle_adb_configure
from .system import handle_build_progress, handle_system_info

HANDLERS = {
    "chat": handle_chat,
    "execute": handle_execute,
    "read_file": handle_read_file,
    "write_file": handle_write_file,
    "delete_file": handle_delete_file,
    "list_dir": handle_list_dir,
    "build_progress": handle_build_progress,
    "screen_stream": handle_screen_stream,
    "continuous_stream": handle_continuous_stream,
    "mouse_event": handle_mouse_event,
    "keyboard_event": handle_keyboard_event,
    "system_info": handle_system_info,
    "device_list": handle_device_list,
    "device_command": handle_device_command,
    "adb_configure": handle_adb_configure,
}

NO_AUTH_REQUIRED = {"ping", "system_info"}
