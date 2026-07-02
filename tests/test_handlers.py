"""Tests for MiMo Mobile Server handlers."""

import unittest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from protocol import encode_ws_frame, websocket_handshake, send_json
from handlers.files import handle_read_file, handle_write_file, handle_list_dir
from handlers.chat import handle_chat
from handlers.execute import handle_execute
from state import SessionStore


class TestWebSocketFrameEncoding(unittest.TestCase):
    """Test WebSocket frame encoding/decoding"""

    def test_encode_simple_text_frame(self):
        data = "Hello"
        frame = encode_ws_frame(data)
        self.assertEqual(frame[0], 0x81)
        self.assertEqual(frame[1], 5)
        self.assertEqual(frame[2:], b"Hello")

    def test_encode_json_message(self):
        msg = {"type": "chat", "data": "test"}
        json_str = json.dumps(msg)
        frame = encode_ws_frame(json_str)
        self.assertEqual(frame[0], 0x81)
        decoded = frame[2:].decode()
        self.assertIn('"type"', decoded)

    def test_encode_large_frame(self):
        data = "x" * 200
        frame = encode_ws_frame(data)
        self.assertEqual(frame[0], 0x81)
        self.assertEqual(frame[1], 126)


class TestMessageHandlers(unittest.IsolatedAsyncioTestCase):
    """Test message handler functions"""

    async def test_handle_auth_success(self):
        from server import handle_message

        writer = AsyncMock()
        msg = json.dumps({"type": "auth", "id": "test-1", "pin": "MIMO2026"})
        await handle_message(msg, writer, ("127.0.0.1", 12345))
        writer.write.assert_called()

    async def test_handle_auth_failure(self):
        from server import handle_message

        writer = AsyncMock()
        msg = json.dumps({"type": "auth", "id": "test-2", "pin": "WRONGPIN"})
        await handle_message(msg, writer, ("127.0.0.1", 12345))
        writer.write.assert_called()

    async def test_handle_ping(self):
        from server import handle_message

        writer = AsyncMock()
        msg = json.dumps({"type": "ping", "id": "test-3"})
        await handle_message(msg, writer)
        writer.write.assert_called()


class TestFileOperations(unittest.IsolatedAsyncioTestCase):
    """Test file operation handlers"""

    async def test_read_file(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("Test content")
            temp_file = f.name
        try:
            writer = AsyncMock()
            msg = {"id": "test-4", "path": temp_file}
            await handle_read_file(msg, writer)
            writer.write.assert_called()
        finally:
            Path(temp_file).unlink()

    async def test_write_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            writer = AsyncMock()
            msg = {"id": "test-5", "path": str(test_file), "content": "Test content"}
            await handle_write_file(msg, writer)
            self.assertTrue(test_file.exists())
            self.assertEqual(test_file.read_text(), "Test content")

    async def test_list_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "file1.txt").touch()
            Path(tmpdir, "file2.txt").touch()
            Path(tmpdir, "subdir").mkdir()
            writer = AsyncMock()
            msg = {"id": "test-6", "path": tmpdir}
            await handle_list_dir(msg, writer)
            writer.write.assert_called()


class TestChatHandler(unittest.IsolatedAsyncioTestCase):
    """Test chat message handler"""

    @patch('handlers.chat.MIMO_CMD', '/bin/echo')
    @patch('handlers.chat.WORKSPACE', '/tmp')
    async def test_handle_chat_echo(self):
        writer = AsyncMock()
        msg = {"id": "test-7", "prompt": "hello world", "instance_id": "default"}
        await handle_chat(msg, writer)
        calls = [call for call in writer.write.call_args_list]
        self.assertGreater(len(calls), 0)


class TestExecuteHandler(unittest.IsolatedAsyncioTestCase):
    """Test execute command handler"""

    @patch('handlers.execute.WORKSPACE', '/tmp')
    async def test_handle_execute_echo(self):
        writer = AsyncMock()
        msg = {"id": "test-8", "command": "echo 'hello'"}
        await handle_execute(msg, writer)
        writer.write.assert_called()

    async def test_handle_execute_with_cwd(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = AsyncMock()
            msg = {"id": "test-9", "command": "pwd", "cwd": tmpdir}
            await handle_execute(msg, writer)
            writer.write.assert_called()


class TestWebSocketProtocol(unittest.TestCase):
    """Test WebSocket protocol handler"""

    def test_protocol_initialization(self):
        from server import WebSocketProtocol
        protocol = WebSocketProtocol()
        transport = MagicMock()
        transport.get_extra_info.return_value = ("127.0.0.1", 12345)
        protocol.connection_made(transport)
        self.assertFalse(protocol.handshake_done)
        self.assertEqual(protocol.buf, b"")
        self.assertEqual(protocol.addr, ("127.0.0.1", 12345))

    def test_websocket_handshake(self):
        key = "dGhlIHNhbXBsZSBub25jZQ=="
        response = websocket_handshake(key)
        self.assertIn("101 Switching Protocols", response)
        self.assertIn("Upgrade: websocket", response)
        self.assertIn("Sec-WebSocket-Accept", response)


class TestErrorHandling(unittest.IsolatedAsyncioTestCase):
    """Test error handling"""

    async def test_invalid_json(self):
        from server import handle_message
        writer = AsyncMock()
        msg = "not valid json{"
        await handle_message(msg, writer)
        writer.write.assert_called()

    async def test_unknown_message_type(self):
        from server import handle_message
        writer = AsyncMock()
        msg = json.dumps({"type": "unknown_type", "id": "test-10"})
        await handle_message(msg, writer)
        writer.write.assert_called()

    @patch('handlers.chat.WORKSPACE', '/tmp')
    async def test_missing_required_field(self):
        from server import handle_message
        writer = AsyncMock()
        msg = json.dumps({"type": "chat"})
        await handle_message(msg, writer)
        writer.write.assert_called()


class TestSessionStore(unittest.TestCase):
    """Test session state management"""

    def test_authorize_and_check(self):
        store = SessionStore()
        store.authorize(("127.0.0.1", 12345))
        self.assertTrue(store.is_authorized(("127.0.0.1", 12345)))
        self.assertFalse(store.is_authorized(("192.168.1.1", 9999)))

    def test_deauthorize(self):
        store = SessionStore()
        store.authorize(("127.0.0.1", 12345))
        store.deauthorize(("127.0.0.1", 12345))
        self.assertFalse(store.is_authorized(("127.0.0.1", 12345)))

    def test_client_tracking(self):
        store = SessionStore()
        mock_client = MagicMock()
        store.add_client(mock_client)
        self.assertEqual(store.client_count(), 1)
        store.remove_client(mock_client)
        self.assertEqual(store.client_count(), 0)


class TestMetrics(unittest.TestCase):
    """Test Prometheus metrics"""

    def test_metrics_endpoint(self):
        from metrics import get_metrics, WS_CONNECTIONS, CHAT_COMMANDS
        WS_CONNECTIONS.set(5)
        CHAT_COMMANDS.inc()
        output = get_metrics()
        self.assertIn(b"mimo_ws_connections_active", output)
        self.assertIn(b"mimo_chat_commands_total", output)


if __name__ == '__main__':
    unittest.main()
