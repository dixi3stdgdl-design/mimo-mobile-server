"""Comprehensive integration tests for all handlers."""

import unittest
import asyncio
import json
import struct
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from handlers.chat import handle_chat
from handlers.execute import handle_execute
from handlers.files import handle_read_file, handle_write_file, handle_delete_file, handle_list_dir
from handlers.screen import handle_screen_stream, handle_mouse_event, handle_keyboard_event
from handlers.adb import handle_device_list, handle_device_command
from handlers.system import handle_system_info
from state import SessionStore
from protocol import send_json


def decode_ws_frame(data):
    """Decode a WebSocket frame and return the JSON payload."""
    if len(data) < 2:
        return None
    opcode = data[0] & 0x0F
    length = data[1] & 0x7F
    offset = 2
    if length == 126:
        if len(data) < 4:
            return None
        length = struct.unpack(">H", data[2:4])[0]
        offset = 4
    elif length == 127:
        if len(data) < 10:
            return None
        length = struct.unpack(">Q", data[2:10])[0]
        offset = 10
    if len(data) < offset + length:
        return None
    payload = data[offset:offset + length]
    return json.loads(payload.decode("utf-8"))


def get_messages(writer):
    """Extract all JSON messages from writer.write calls."""
    messages = []
    for call in writer.write.call_args_list:
        data = call.args[0] if call.args else None
        if data:
            try:
                msg = decode_ws_frame(data)
                if msg:
                    messages.append(msg)
            except Exception:
                pass
    return messages


class TestChatHandler(unittest.IsolatedAsyncioTestCase):
    """Test chat handler with mimo CLI."""

    @patch('handlers.chat.MIMO_CMD', '/bin/echo')
    @patch('handlers.chat.WORKSPACE', '/tmp')
    async def test_chat_start_message(self):
        writer = AsyncMock()
        msg = {"id": "chat-1", "prompt": "hello world", "instance_id": "default"}
        await handle_chat(msg, writer)
        messages = get_messages(writer)
        types = [m.get("type") for m in messages]
        self.assertIn("chat_start", types)
        self.assertIn("chat_end", types)

    @patch('handlers.chat.MIMO_CMD', '/bin/echo')
    @patch('handlers.chat.WORKSPACE', '/tmp')
    async def test_chat_instance_id(self):
        writer = AsyncMock()
        msg = {"id": "chat-2", "prompt": "test", "instance_id": "myinstance"}
        await handle_chat(msg, writer)
        messages = get_messages(writer)
        start_msg = next(m for m in messages if m.get("type") == "chat_start")
        self.assertEqual(start_msg["instance_id"], "myinstance")

    @patch('handlers.chat.MIMO_CMD', '/nonexistent_command')
    @patch('handlers.chat.WORKSPACE', '/tmp')
    async def test_chat_command_not_found(self):
        writer = AsyncMock()
        msg = {"id": "chat-3", "prompt": "test"}
        await handle_chat(msg, writer)
        messages = get_messages(writer)
        end_msg = next(m for m in messages if m.get("type") == "chat_end")
        self.assertIn("error", end_msg)

    @patch('handlers.chat.MIMO_CMD', '/bin/echo')
    @patch('handlers.chat.WORKSPACE', '/tmp')
    async def test_chat_with_state(self):
        writer = AsyncMock()
        state = SessionStore()
        msg = {"id": "chat-4", "prompt": "test"}
        await handle_chat(msg, writer, state)
        self.assertNotIn("chat-4", state.processes)


class TestExecuteHandler(unittest.IsolatedAsyncioTestCase):
    """Test execute command handler."""

    @patch('handlers.execute.WORKSPACE', '/tmp')
    async def test_execute_echo(self):
        writer = AsyncMock()
        msg = {"id": "exec-1", "command": "echo 'hello world'"}
        await handle_execute(msg, writer)
        messages = get_messages(writer)
        types = [m.get("type") for m in messages]
        self.assertIn("exec_start", types)
        self.assertIn("exec_end", types)
        outputs = [m for m in messages if m.get("type") == "exec_output"]
        self.assertTrue(any("hello world" in o.get("data", "") for o in outputs))

    @patch('handlers.execute.WORKSPACE', '/tmp')
    async def test_execute_with_cwd(self):
        writer = AsyncMock()
        msg = {"id": "exec-2", "command": "pwd", "cwd": "/tmp"}
        await handle_execute(msg, writer)
        messages = get_messages(writer)
        outputs = [m for m in messages if m.get("type") == "exec_output"]
        self.assertTrue(any("/tmp" in o.get("data", "") for o in outputs))

    @patch('handlers.execute.WORKSPACE', '/tmp')
    async def test_execute_exit_code(self):
        writer = AsyncMock()
        msg = {"id": "exec-3", "command": "exit 42"}
        await handle_execute(msg, writer)
        messages = get_messages(writer)
        end_msg = next(m for m in messages if m.get("type") == "exec_end")
        self.assertEqual(end_msg["exit_code"], 42)

    @patch('handlers.execute.WORKSPACE', '/tmp')
    async def test_execute_stderr(self):
        writer = AsyncMock()
        msg = {"id": "exec-4", "command": "echo error >&2"}
        await handle_execute(msg, writer)
        messages = get_messages(writer)
        outputs = [m for m in messages if m.get("type") == "exec_output"]
        self.assertTrue(any("error" in o.get("data", "") for o in outputs))

    @patch('handlers.execute.WORKSPACE', '/tmp')
    async def test_execute_with_state(self):
        writer = AsyncMock()
        state = SessionStore()
        msg = {"id": "exec-5", "command": "sleep 0.1"}
        await handle_execute(msg, writer, state)
        self.assertNotIn("exec-5", state.processes)

    @patch('handlers.execute.WORKSPACE', '/tmp')
    async def test_execute_instance_id(self):
        writer = AsyncMock()
        msg = {"id": "exec-6", "command": "echo test", "instance_id": "inst1"}
        await handle_execute(msg, writer)
        messages = get_messages(writer)
        self.assertTrue(any(m.get("type") == "exec_end" for m in messages))


class TestFileOperations(unittest.IsolatedAsyncioTestCase):
    """Test file operation handlers."""

    async def test_read_file_success(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("Test content here")
            temp_file = f.name
        try:
            writer = AsyncMock()
            msg = {"id": "file-1", "path": temp_file}
            await handle_read_file(msg, writer)
            messages = get_messages(writer)
            file_msg = next(m for m in messages if m.get("type") == "file_content")
            self.assertEqual(file_msg["data"], "Test content here")
        finally:
            Path(temp_file).unlink()

    async def test_read_file_not_found(self):
        writer = AsyncMock()
        msg = {"id": "file-2", "path": "/nonexistent/file.txt"}
        await handle_read_file(msg, writer)
        messages = get_messages(writer)
        error_msg = next(m for m in messages if m.get("type") == "error")
        self.assertIn("data", error_msg)

    async def test_write_file_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test_write.txt"
            writer = AsyncMock()
            msg = {"id": "file-3", "path": str(test_file), "content": "Written content"}
            await handle_write_file(msg, writer)
            self.assertTrue(test_file.exists())
            self.assertEqual(test_file.read_text(), "Written content")
            messages = get_messages(writer)
            self.assertTrue(any(m.get("type") == "file_written" for m in messages))

    async def test_write_file_creates_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "subdir" / "nested" / "test.txt"
            writer = AsyncMock()
            msg = {"id": "file-4", "path": str(test_file), "content": "nested"}
            await handle_write_file(msg, writer)
            self.assertTrue(test_file.exists())

    async def test_delete_file_success(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_file = f.name
        try:
            writer = AsyncMock()
            msg = {"id": "file-5", "path": temp_file}
            await handle_delete_file(msg, writer)
            self.assertFalse(Path(temp_file).exists())
            messages = get_messages(writer)
            self.assertTrue(any(m.get("type") == "file_deleted" for m in messages))
        except Exception:
            if Path(temp_file).exists():
                Path(temp_file).unlink()
            raise

    async def test_delete_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir) / "to_delete"
            test_dir.mkdir()
            (test_dir / "file.txt").touch()
            writer = AsyncMock()
            msg = {"id": "file-6", "path": str(test_dir)}
            await handle_delete_file(msg, writer)
            self.assertFalse(test_dir.exists())

    async def test_list_dir_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file1.txt").touch()
            Path(tmpdir, "file2.txt").touch()
            Path(tmpdir, "subdir").mkdir()
            writer = AsyncMock()
            msg = {"id": "file-7", "path": tmpdir}
            await handle_list_dir(msg, writer)
            messages = get_messages(writer)
            list_msg = next(m for m in messages if m.get("type") == "dir_listing")
            self.assertEqual(len(list_msg["entries"]), 3)
            names = [e["name"] for e in list_msg["entries"]]
            self.assertIn("file1.txt", names)
            self.assertIn("subdir", names)

    async def test_list_dir_not_found(self):
        writer = AsyncMock()
        msg = {"id": "file-8", "path": "/nonexistent_dir"}
        await handle_list_dir(msg, writer)
        messages = get_messages(writer)
        self.assertTrue(any(m.get("type") == "error" for m in messages))

    async def test_list_dir_entries_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "test.txt").write_text("hello")
            writer = AsyncMock()
            msg = {"id": "file-9", "path": tmpdir}
            await handle_list_dir(msg, writer)
            messages = get_messages(writer)
            list_msg = next(m for m in messages if m.get("type") == "dir_listing")
            entry = list_msg["entries"][0]
            self.assertIn("name", entry)
            self.assertIn("is_dir", entry)
            self.assertIn("size", entry)


class TestScreenHandlers(unittest.IsolatedAsyncioTestCase):
    """Test screen capture and input handlers."""

    @patch('handlers.screen.subprocess.run')
    async def test_screen_capture_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="base64data")
        writer = AsyncMock()
        msg = {"id": "screen-1", "action": "capture"}
        await handle_screen_stream(msg, writer)
        messages = get_messages(writer)
        frame_msg = next(m for m in messages if m.get("type") == "screen_frame")
        self.assertEqual(frame_msg["data"], "base64data")
        self.assertEqual(frame_msg["format"], "jpeg")

    @patch('handlers.screen.subprocess.run')
    async def test_screen_capture_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        writer = AsyncMock()
        msg = {"id": "screen-2", "action": "capture"}
        await handle_screen_stream(msg, writer)
        messages = get_messages(writer)
        frame_msg = next(m for m in messages if m.get("type") == "screen_frame")
        self.assertIn("error", frame_msg)

    async def test_screen_start_stream(self):
        writer = AsyncMock()
        msg = {"id": "screen-3", "action": "start_stream"}
        await handle_screen_stream(msg, writer)
        messages = get_messages(writer)
        status_msg = next(m for m in messages if m.get("type") == "screen_stream_status")
        self.assertEqual(status_msg["data"], "started")

    async def test_screen_stop_stream(self):
        writer = AsyncMock()
        msg = {"id": "screen-4", "action": "stop_stream"}
        await handle_screen_stream(msg, writer)
        messages = get_messages(writer)
        status_msg = next(m for m in messages if m.get("type") == "screen_stream_status")
        self.assertEqual(status_msg["data"], "stopped")


class TestMouseKeyboardHandlers(unittest.IsolatedAsyncioTestCase):
    """Test mouse and keyboard event handlers."""

    @patch('handlers.screen.subprocess.run')
    async def test_mouse_click(self, mock_run):
        mock_run.return_value = MagicMock()
        writer = AsyncMock()
        msg = {"id": "mouse-1", "x": 100, "y": 200, "action": "click", "button": "left"}
        await handle_mouse_event(msg, writer)
        messages = get_messages(writer)
        ack_msg = next(m for m in messages if m.get("type") == "mouse_ack")
        self.assertEqual(ack_msg["data"], "ok")

    @patch('handlers.screen.subprocess.run')
    async def test_mouse_move(self, mock_run):
        mock_run.return_value = MagicMock()
        writer = AsyncMock()
        msg = {"id": "mouse-2", "x": 50, "y": 50, "action": "move"}
        await handle_mouse_event(msg, writer)
        messages = get_messages(writer)
        ack_msg = next(m for m in messages if m.get("type") == "mouse_ack")
        self.assertEqual(ack_msg["data"], "ok")

    @patch('handlers.screen.subprocess.run')
    async def test_mouse_scroll(self, mock_run):
        mock_run.return_value = MagicMock()
        writer = AsyncMock()
        msg = {"id": "mouse-3", "x": 100, "y": 100, "action": "scroll", "delta": 240}
        await handle_mouse_event(msg, writer)
        messages = get_messages(writer)
        ack_msg = next(m for m in messages if m.get("type") == "mouse_ack")
        self.assertEqual(ack_msg["data"], "ok")

    @patch('handlers.screen.subprocess.run')
    async def test_keyboard_type(self, mock_run):
        mock_run.return_value = MagicMock()
        writer = AsyncMock()
        msg = {"id": "kb-1", "key": "hello", "action": "type"}
        await handle_keyboard_event(msg, writer)
        messages = get_messages(writer)
        ack_msg = next(m for m in messages if m.get("type") == "keyboard_ack")
        self.assertEqual(ack_msg["data"], "ok")

    @patch('handlers.screen.subprocess.run')
    async def test_keyboard_hotkey(self, mock_run):
        mock_run.return_value = MagicMock()
        writer = AsyncMock()
        msg = {"id": "kb-2", "key": "ctrl+c", "action": "hotkey"}
        await handle_keyboard_event(msg, writer)
        messages = get_messages(writer)
        ack_msg = next(m for m in messages if m.get("type") == "keyboard_ack")
        self.assertEqual(ack_msg["data"], "ok")


class TestADBHandlers(unittest.IsolatedAsyncioTestCase):
    """Test ADB device management handlers."""

    @patch('handlers.adb.subprocess.run')
    async def test_device_list(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="List of devices attached\nabc123\tdevice product/model: Pixel 6\n"
        )
        writer = AsyncMock()
        msg = {"id": "adb-1"}
        await handle_device_list(msg, writer)
        messages = get_messages(writer)
        list_msg = next(m for m in messages if m.get("type") == "device_list")
        self.assertEqual(len(list_msg["data"]), 1)
        self.assertEqual(list_msg["data"][0]["serial"], "abc123")

    @patch('handlers.adb.subprocess.run')
    async def test_device_list_empty(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="List of devices attached\n\n"
        )
        writer = AsyncMock()
        msg = {"id": "adb-2"}
        await handle_device_list(msg, writer)
        messages = get_messages(writer)
        list_msg = next(m for m in messages if m.get("type") == "device_list")
        self.assertEqual(len(list_msg["data"]), 0)

    @patch('handlers.adb.subprocess.run')
    async def test_device_command_shell(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="output",
            stderr=""
        )
        writer = AsyncMock()
        msg = {"id": "adb-3", "serial": "abc123", "command": "ls", "action": "shell"}
        await handle_device_command(msg, writer)
        messages = get_messages(writer)
        out_msg = next(m for m in messages if m.get("type") == "device_output")
        self.assertEqual(out_msg["stdout"], "output")
        self.assertEqual(out_msg["exit_code"], 0)

    @patch('handlers.adb.subprocess.run')
    async def test_device_command_install(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Success", stderr="")
        writer = AsyncMock()
        msg = {"id": "adb-4", "serial": "abc123", "action": "install", "apk_path": "/tmp/app.apk"}
        await handle_device_command(msg, writer)
        messages = get_messages(writer)
        out_msg = next(m for m in messages if m.get("type") == "device_output")
        self.assertEqual(out_msg["exit_code"], 0)

    @patch('handlers.adb.subprocess.run')
    async def test_device_command_launch(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        writer = AsyncMock()
        msg = {"id": "adb-5", "serial": "abc123", "action": "launch", "component": "com.app/.MainActivity"}
        await handle_device_command(msg, writer)
        messages = get_messages(writer)
        out_msg = next(m for m in messages if m.get("type") == "device_output")
        self.assertEqual(out_msg["exit_code"], 0)

    @patch('handlers.adb.subprocess.run')
    async def test_device_command_input_text(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        writer = AsyncMock()
        msg = {"id": "adb-6", "serial": "abc123", "action": "input", "input_type": "text", "value": "hello"}
        await handle_device_command(msg, writer)
        messages = get_messages(writer)
        out_msg = next(m for m in messages if m.get("type") == "device_output")
        self.assertEqual(out_msg["exit_code"], 0)

    @patch('handlers.adb.subprocess.run')
    async def test_device_command_input_tap(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        writer = AsyncMock()
        msg = {"id": "adb-7", "serial": "abc123", "action": "input", "input_type": "tap", "value": "100,200"}
        await handle_device_command(msg, writer)
        messages = get_messages(writer)
        out_msg = next(m for m in messages if m.get("type") == "device_output")
        self.assertEqual(out_msg["exit_code"], 0)

    @patch('handlers.adb.subprocess.run')
    async def test_device_command_screenshot(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        writer = AsyncMock()
        msg = {"id": "adb-8", "serial": "abc123", "action": "screenshot"}
        await handle_device_command(msg, writer)
        messages = get_messages(writer)
        out_msg = next(m for m in messages if m.get("type") == "device_output")
        self.assertIn("Screenshot saved", out_msg["stdout"])


class TestSystemHandler(unittest.IsolatedAsyncioTestCase):
    """Test system info handler."""

    async def test_system_info(self):
        writer = AsyncMock()
        msg = {"id": "sys-1"}
        await handle_system_info(msg, writer)
        messages = get_messages(writer)
        info_msg = next(m for m in messages if m.get("type") == "system_info")
        self.assertIn("data", info_msg)
        self.assertIn("platform", info_msg["data"])


class TestServerHandleMessage(unittest.IsolatedAsyncioTestCase):
    """Test main server message routing."""

    async def test_handle_auth_success(self):
        from server import handle_message
        writer = AsyncMock()
        msg = json.dumps({"type": "auth", "id": "auth-1", "pin": "MIMO2026"})
        await handle_message(msg, writer, ("127.0.0.1", 12345))
        messages = get_messages(writer)
        auth_msg = next(m for m in messages if m.get("type") == "auth_result")
        self.assertEqual(auth_msg["status"], "ok")

    async def test_handle_auth_failure(self):
        from server import handle_message
        writer = AsyncMock()
        msg = json.dumps({"type": "auth", "id": "auth-2", "pin": "WRONGPIN"})
        await handle_message(msg, writer, ("127.0.0.1", 12345))
        messages = get_messages(writer)
        auth_msg = next(m for m in messages if m.get("type") == "auth_result")
        self.assertEqual(auth_msg["status"], "error")

    async def test_handle_ping(self):
        from server import handle_message
        writer = AsyncMock()
        msg = json.dumps({"type": "ping", "id": "ping-1"})
        await handle_message(msg, writer)
        messages = get_messages(writer)
        pong_msg = next(m for m in messages if m.get("type") == "pong")
        self.assertIsNotNone(pong_msg)

    async def test_invalid_json(self):
        from server import handle_message
        writer = AsyncMock()
        await handle_message("not valid json{", writer)
        messages = get_messages(writer)
        error_msg = next(m for m in messages if m.get("type") == "error")
        self.assertIn("Invalid JSON", error_msg["data"])

    async def test_unknown_type(self):
        from server import handle_message
        writer = AsyncMock()
        msg = json.dumps({"type": "unknown_type", "id": "unk-1"})
        await handle_message(msg, writer)
        messages = get_messages(writer)
        error_msg = next(m for m in messages if m.get("type") == "error")
        self.assertIn("Unknown type", error_msg["data"])

    async def test_unauthorized_message(self):
        from server import handle_message
        writer = AsyncMock()
        msg = json.dumps({"type": "chat", "id": "unauth-1", "prompt": "test"})
        await handle_message(msg, writer, ("192.168.1.100", 9999))
        messages = get_messages(writer)
        error_msg = next(m for m in messages if m.get("type") == "error")
        self.assertIn("Not authorized", error_msg["data"])

    async def test_get_token_unauthenticated(self):
        from server import handle_message
        writer = AsyncMock()
        writer.user_id = None  # Simulate unauthenticated user
        msg = json.dumps({"type": "get_token", "id": "token-1"})
        await handle_message(msg, writer)
        messages = get_messages(writer)
        error_msg = next(m for m in messages if m.get("type") == "error")
        self.assertIn("Not authenticated", error_msg["data"])


if __name__ == '__main__':
    unittest.main()
