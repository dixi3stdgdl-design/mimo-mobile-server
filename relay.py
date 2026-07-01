#!/usr/bin/env python3
"""
MiMo Cloud Relay - Universal connection for mobile data
Exposes the local WebSocket server to the internet via a simple relay.
"""
import asyncio
import hashlib
import base64
import struct
import json
import sys

RELAY_HOST = "0.0.0.0"
RELAY_PORT = 9876  # Public relay port
LOCAL_WS = "127.0.0.1"
LOCAL_PORT = 8765
AUTH_PIN = "MIMO2026"  # Must match server PIN

clients = {}  # relay_writer -> local_reader
locals = {}   # local_writer -> relay_reader


def ws_handshake(key):
    magic = "258EAFA5-E914-47DA-95CA-5AB9A50E6596"
    accept = base64.b64encode(hashlib.sha1((key + magic).encode()).digest()).decode()
    return f"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: {accept}\r\n\r\n"


def encode_frame(data):
    if isinstance(data, str):
        data = data.encode()
    length = len(data)
    frame = bytearray([0x81])
    if length < 126:
        frame.append(length)
    elif length < 65536:
        frame.append(126)
        frame.extend(struct.pack(">H", length))
    else:
        frame.append(127)
        frame.extend(struct.pack(">Q", length))
    frame.extend(data)
    return bytes(frame)


async def handle_client(reader, writer):
    addr = writer.get_extra_info("peername")
    print(f"[RELAY] Client connected: {addr}", flush=True)

    try:
        # HTTP upgrade
        data = await asyncio.wait_for(reader.read(4096), timeout=10)
        header = data.decode("utf-8", errors="replace")
        if "Upgrade: websocket" not in header and "Upgrade: WebSocket" not in header:
            writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            await writer.drain()
            writer.close()
            return

        ws_key = None
        for line in header.split("\r\n"):
            if line.lower().startswith("sec-websocket-key:"):
                ws_key = line.split(":", 1)[1].strip()
                break

        if not ws_key:
            writer.close()
            return

        writer.write(ws_handshake(ws_key).encode())
        await writer.drain()

        # Connect to local MiMo server
        local_reader, local_writer = await asyncio.open_connection(LOCAL_WS, LOCAL_PORT)
        print(f"[RELAY] Connected to local server for {addr}", flush=True)

        async def relay_local():
            """Forward local server -> relay client"""
            try:
                while True:
                    data = await local_reader.read(65536)
                    if not data:
                        break
                    writer.write(data)
                    await writer.drain()
            except Exception:
                pass
            finally:
                try:
                    writer.close()
                except Exception:
                    pass

        async def relay_client():
            """Forward relay client -> local server"""
            try:
                while True:
                    data = await reader.read(65536)
                    if not data:
                        break
                    local_writer.write(data)
                    await local_writer.drain()
            except Exception:
                pass
            finally:
                try:
                    local_writer.close()
                except Exception:
                    pass

        # Run both relays
        await asyncio.gather(relay_local(), relay_client())

    except Exception as e:
        print(f"[RELAY] Error: {e}", flush=True)
    finally:
        print(f"[RELAY] Client disconnected: {addr}", flush=True)


async def main():
    print("=" * 50, flush=True)
    print("  MiMo Cloud Relay", flush=True)
    print(f"  Public:   ws://0.0.0.0:{RELAY_PORT}", flush=True)
    print(f"  Local:    ws://{LOCAL_WS}:{LOCAL_PORT}", flush=True)
    print("=" * 50, flush=True)

    server = await asyncio.start_server(handle_client, RELAY_HOST, RELAY_PORT)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
