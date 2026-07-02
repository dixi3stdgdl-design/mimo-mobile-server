#!/usr/bin/env python3
"""
MiMo Mobile Server — Modular architecture
Bridges Android app with MiMo Code CLI
"""

import asyncio
import json
import time
import struct
import threading
import sys

from config import HOST, WS_PORT, HTTP_PORT, WORKSPACE, AUTH_PIN, REDIS_URL
from protocol import websocket_handshake, encode_ws_frame, send_json
from state import SessionStore, RedisSessionStore
from handlers import HANDLERS, NO_AUTH_REQUIRED
from metrics import WS_CONNECTIONS, WS_MESSAGES, WS_AUTH_FAILURES, ACTIVE_PROCESSES, start_uptime_thread
from http_handler import start_http_server


def create_session_store():
    if REDIS_URL:
        try:
            return RedisSessionStore(REDIS_URL)
        except Exception as e:
            print(f"[STATE] Redis unavailable ({e}), falling back to memory", flush=True)
    return SessionStore()


state = create_session_store()


class WebSocketProtocol(asyncio.Protocol):
    def connection_made(self, transport):
        self.transport = transport
        self.buf = b""
        self.handshake_done = False
        self.addr = transport.get_extra_info("peername")
        self.last_pong = time.time()
        self.last_activity = time.time()
        print(f"[WS] Connection from {self.addr}", flush=True)

    def data_received(self, data):
        self.buf += data
        self.last_activity = time.time()
        if not self.handshake_done:
            idx = self.buf.find(b"\r\n\r\n")
            if idx == -1:
                return
            header = self.buf[:idx].decode("utf-8", errors="replace")
            self.buf = self.buf[idx + 4:]
            if "Upgrade: websocket" not in header and "Upgrade: WebSocket" not in header:
                self.transport.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                self.transport.close()
                return
            ws_key = None
            for line in header.split("\r\n"):
                if line.lower().startswith("sec-websocket-key:"):
                    ws_key = line.split(":", 1)[1].strip()
                    break
            if not ws_key:
                self.transport.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                self.transport.close()
                return
            self.transport.write(websocket_handshake(ws_key).encode())
            self.handshake_done = True
            state.add_client(self)
            WS_CONNECTIONS.set(state.client_count())
            print(f"[WS] Client connected: {self.addr}", flush=True)
            if self.buf:
                self._process_frames()
        else:
            self._process_frames()

    def _process_frames(self):
        while len(self.buf) >= 2:
            b1 = self.buf[0] & 0xFF
            b2 = self.buf[1] & 0xFF
            opcode = b1 & 0x0F
            if opcode not in (0, 1, 2, 8, 9, 10):
                self.buf = self.buf[1:]
                continue
            if opcode == 0x08:
                self.buf = self.buf[2:]
                self.close()
                return
            if opcode == 0x09:
                self.buf = self.buf[2:]
                pong_frame = bytearray([0x8A, 0x00])
                try:
                    self.transport.write(bytes(pong_frame))
                except Exception:
                    pass
                continue
            if opcode == 0x0A:
                self.buf = self.buf[2:]
                self.last_pong = time.time()
                continue
            length = self.buf[1] & 0x7F
            masked = self.buf[1] & 0x80
            offset = 2
            if length == 126:
                if len(self.buf) < 4:
                    return
                length = struct.unpack(">H", self.buf[2:4])[0]
                offset = 4
            elif length == 127:
                if len(self.buf) < 10:
                    return
                length = struct.unpack(">Q", self.buf[2:10])[0]
                offset = 10
            if masked:
                if len(self.buf) < offset + 4:
                    return
                mask = self.buf[offset:offset + 4]
                offset += 4
            if len(self.buf) < offset + length:
                return
            payload = bytearray(self.buf[offset:offset + length])
            if masked:
                payload = bytearray(b ^ mask[i % 4] for i, b in enumerate(payload))
            self.buf = self.buf[offset + length:]
            if payload:
                msg_text = bytes(payload).decode("utf-8", errors="replace")
                asyncio.ensure_future(self._handle(msg_text))

    async def _handle(self, msg_text):
        try:
            await handle_message(msg_text, self, self.addr)
        except Exception as e:
            print(f"[WS] Handle error: {e}", flush=True)

    def write(self, data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        try:
            self.transport.write(data)
        except Exception:
            pass

    def close(self):
        try:
            self.transport.close()
        except Exception:
            pass

    def connection_lost(self, exc):
        state.remove_client(self)
        if self.addr:
            state.deauthorize(self.addr)
        WS_CONNECTIONS.set(state.client_count())
        print(f"[WS] Client disconnected: {self.addr}", flush=True)


async def handle_message(message, writer, client_addr=None):
    try:
        msg = json.loads(message)
    except json.JSONDecodeError:
        await send_json(writer, {"type": "error", "data": "Invalid JSON"})
        return

    msg_type = msg.get("type")
    msg_id = msg.get("id")

    WS_MESSAGES.labels(msg_type=msg_type).inc()

    if msg_type == "auth":
        pin = msg.get("pin", "")
        if pin == AUTH_PIN:
            if client_addr:
                state.authorize(client_addr)
            await send_json(writer, {"type": "auth_result", "id": msg_id, "data": "authorized", "status": "ok"})
            print(f"[WS] Device authorized: {client_addr}", flush=True)
        else:
            WS_AUTH_FAILURES.inc()
            await send_json(writer, {"type": "auth_result", "id": msg_id, "data": "denied", "status": "error"})
            print(f"[WS] Auth failed: {client_addr}", flush=True)
        return

    if client_addr and not state.is_authorized(client_addr):
        if msg_type not in NO_AUTH_REQUIRED:
            await send_json(writer, {"type": "error", "id": msg_id, "data": "Not authorized. Send auth message first."})
            return

    handler = HANDLERS.get(msg_type)
    if handler:
        await handler(msg, writer, state)
    elif msg_type == "ping":
        await send_json(writer, {"type": "pong", "id": msg_id})
    else:
        await send_json(writer, {"type": "error", "data": f"Unknown type: {msg_type}"})


async def heartbeat():
    while True:
        await asyncio.sleep(30)
        now = time.time()
        dead = []
        for client in list(state.connected_clients):
            if not client.handshake_done:
                continue
            if now - client.last_activity > 120:
                dead.append(client)
                continue
            try:
                ping_frame = bytearray([0x89, 0x00])
                client.transport.write(bytes(ping_frame))
            except Exception:
                dead.append(client)
        for client in dead:
            print(f"[WS] Heartbeat timeout: {client.addr}", flush=True)
            client.close()
        alive = len(state.connected_clients) - len(dead)
        if alive > 0 or len(dead) > 0:
            print(f"[WS] Heartbeat: {alive} alive, {len(dead)} removed", flush=True)


def main():
    print("=" * 50, flush=True)
    print("  MiMo Mobile Server", flush=True)
    print(f"  Workspace: {WORKSPACE}", flush=True)
    print(f"  WebSocket: ws://0.0.0.0:{WS_PORT}", flush=True)
    print(f"  HTTP:      http://0.0.0.0:{HTTP_PORT}", flush=True)
    print(f"  State:     {'Redis' if REDIS_URL else 'Memory'}", flush=True)
    print("=" * 50, flush=True)

    start_uptime_thread()

    http_thread = threading.Thread(target=start_http_server, args=(state,), daemon=True)
    http_thread.start()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    server = loop.run_until_complete(
        loop.create_server(WebSocketProtocol, HOST, WS_PORT)
    )
    print(f"[WS] WebSocket server running on ws://{HOST}:{WS_PORT}", flush=True)

    loop.create_task(heartbeat())
    print("[WS] Heartbeat started (30s interval)", flush=True)

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()


if __name__ == "__main__":
    import socket
    try:
        main()
    except OSError as e:
        if "Address already in use" in str(e):
            print(f"[FATAL] Port {WS_PORT} is already in use by another process.", flush=True)
            print(f"[FATAL] Kill the other process or change MIMO_WS_PORT in .env", flush=True)
            print(f"[FATAL] Example: kill -9 $(lsof -t -i:{WS_PORT})", flush=True)
            sys.exit(1)
        raise
