# Testing Setup for MiMo Mobile Server

import unittest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import tempfile
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestWebSocketFrameEncoding(unittest.TestCase):
    """Test WebSocket frame encoding/decoding"""

    def test_encode_simple_text_frame(self):
        """Test encoding simple text frame"""
        from server import encode_ws_frame
        
        data = "Hello"
        frame = encode_ws_frame(data)
        
        # First byte: FIN (1) + RSV (000) + OPCODE (0001 = text)
        self.assertEqual(frame[0], 0x81)
        # Second byte: MASK (0) + length (5)
        self.assertEqual(frame[1], 5)
        # Rest: data
        self.assertEqual(frame[2:], b"Hello")

    def test_encode_json_message(self):
        """Test encoding JSON message"""
        from server import encode_ws_frame
        
        msg = {"type": "chat", "data": "test"}
        json_str = json.dumps(msg)
        frame = encode_ws_frame(json_str)
        
        # Verify frame structure
        self.assertEqual(frame[0], 0x81)
        # Data should be at end
        decoded = frame[2:].decode()
        self.assertIn('"type"', decoded)

    def test_encode_large_frame(self):
        """Test encoding frame larger than 125 bytes"""
        from server import encode_ws_frame
        
        data = "x" * 200
        frame = encode_ws_frame(data)
        
        # Should use 2-byte length
        self.assertEqual(frame[0], 0x81)
        self.assertEqual(frame[1], 126)  # Extended payload length


class TestMessageHandlers(unittest.IsolatedAsyncioTestCase):
    """Test message handler functions"""

    async def test_handle_auth_success(self):
        """Test successful authentication"""
        from server import handle_message
        
        writer = AsyncMock()
        msg = json.dumps({
            "type": "auth",
            "id": "test-1",
            "pin": "MIMO2026"
        })
        
        await handle_message(msg, writer, ("127.0.0.1", 12345))
        
        # Verify response was sent
        writer.write.assert_called()

    async def test_handle_auth_failure(self):
        """Test failed authentication"""
        from server import handle_message
        
        writer = AsyncMock()
        msg = json.dumps({
            "type": "auth",
            "id": "test-2",
            "pin": "WRONGPIN"
        })
        
        await handle_message(msg, writer, ("127.0.0.1", 12345))
        
        # Should reject
        writer.write.assert_called()

    async def test_handle_ping(self):
        """Test ping message"""
        from server import handle_message
        
        writer = AsyncMock()
        msg = json.dumps({
            "type": "ping",
            "id": "test-3"
        })
        
        await handle_message(msg, writer)
        writer.write.assert_called()


class TestFileOperations(unittest.IsolatedAsyncioTestCase):
    """Test file operation handlers"""

    async def test_read_file(self):
        """Test reading file content"""
        from server import handle_read_file, send_json
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("Test content")
            temp_file = f.name
        
        try:
            writer = AsyncMock()
            msg = {
                "id": "test-4",
                "path": temp_file
            }
            
            await handle_read_file(msg, writer)
            
            # Verify send_json was called
            writer.write.assert_called()
        finally:
            Path(temp_file).unlink()

    async def test_write_file(self):
        """Test writing file"""
        from server import handle_write_file
        
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            
            writer = AsyncMock()
            msg = {
                "id": "test-5",
                "path": str(test_file),
                "content": "Test content"
            }
            
            await handle_write_file(msg, writer)
            
            # Verify file was created
            self.assertTrue(test_file.exists())
            self.assertEqual(test_file.read_text(), "Test content")

    async def test_list_directory(self):
        """Test directory listing"""
        from server import handle_list_dir
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            Path(tmpdir, "file1.txt").touch()
            Path(tmpdir, "file2.txt").touch()
            Path(tmpdir, "subdir").mkdir()
            
            writer = AsyncMock()
            msg = {
                "id": "test-6",
                "path": tmpdir
            }
            
            await handle_list_dir(msg, writer)
            writer.write.assert_called()


class TestChatHandler(unittest.IsolatedAsyncioTestCase):
    """Test chat message handler"""

    @patch('server.MIMO_CMD', '/bin/echo')
    async def test_handle_chat_echo(self):
        """Test chat with echo command"""
        from server import handle_chat
        
        writer = AsyncMock()
        msg = {
            "id": "test-7",
            "prompt": "hello world",
            "instance_id": "default"
        }
        
        await handle_chat(msg, writer)
        
        # Should send chat_start and chat_end
        calls = [call for call in writer.write.call_args_list]
        self.assertGreater(len(calls), 0)


class TestExecuteHandler(unittest.IsolatedAsyncioTestCase):
    """Test execute command handler"""

    async def test_handle_execute_echo(self):
        """Test executing echo command"""
        from server import handle_execute
        
        writer = AsyncMock()
        msg = {
            "id": "test-8",
            "command": "echo 'hello'"
        }
        
        await handle_execute(msg, writer)
        
        # Should execute and return output
        writer.write.assert_called()

    async def test_handle_execute_with_cwd(self):
        """Test executing with specific working directory"""
        from server import handle_execute
        
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = AsyncMock()
            msg = {
                "id": "test-9",
                "command": "pwd",
                "cwd": tmpdir
            }
            
            await handle_execute(msg, writer)
            writer.write.assert_called()


class TestWebSocketProtocol(unittest.TestCase):
    """Test WebSocket protocol handler"""

    def test_protocol_initialization(self):
        """Test WebSocketProtocol initialization"""
        from server import WebSocketProtocol
        
        protocol = WebSocketProtocol()
        self.assertFalse(protocol.handshake_done)
        self.assertEqual(protocol.buf, b"")

    def test_websocket_handshake(self):
        """Test WebSocket handshake"""
        from server import websocket_handshake
        
        key = "dGhlIHNhbXBsZSBub25jZQ=="
        response = websocket_handshake(key)
        
        self.assertIn("101 Switching Protocols", response)
        self.assertIn("Upgrade: websocket", response)
        self.assertIn("Sec-WebSocket-Accept", response)


class TestErrorHandling(unittest.IsolatedAsyncioTestCase):
    """Test error handling"""

    async def test_invalid_json(self):
        """Test handling invalid JSON"""
        from server import handle_message
        
        writer = AsyncMock()
        msg = "not valid json{"
        
        await handle_message(msg, writer)
        
        # Should send error
        writer.write.assert_called()

    async def test_unknown_message_type(self):
        """Test unknown message type"""
        from server import handle_message
        
        writer = AsyncMock()
        msg = json.dumps({
            "type": "unknown_type",
            "id": "test-10"
        })
        
        await handle_message(msg, writer)
        writer.write.assert_called()

    async def test_missing_required_field(self):
        """Test message with missing required fields"""
        from server import handle_message
        
        writer = AsyncMock()
        msg = json.dumps({
            "type": "chat"
            # Missing 'prompt' and 'id'
        })
        
        await handle_message(msg, writer)
        writer.write.assert_called()


if __name__ == '__main__':
    unittest.main()
