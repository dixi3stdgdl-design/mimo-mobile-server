"""WebSocket frame encoding/decoding and handshake."""

import hashlib
import base64
import struct
import json


def websocket_handshake(key):
    magic = "258EAFA5-E914-47DA-95CA-5AB9A50E6596"
    accept = base64.b64encode(
        hashlib.sha1((key + magic).encode()).digest()
    ).decode()
    return (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept}\r\n"
        "\r\n"
    )


def encode_ws_frame(data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    length = len(data)
    frame = bytearray()
    frame.append(0x81)
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


def decode_ws_frame(data):
    if len(data) < 2:
        return None, 0
    opcode = data[0] & 0x0F
    masked = data[1] & 0x80
    length = data[1] & 0x7F
    offset = 2
    if length == 126:
        if len(data) < 4:
            return None, 0
        length = struct.unpack(">H", data[2:4])[0]
        offset = 4
    elif length == 127:
        if len(data) < 10:
            return None, 0
        length = struct.unpack(">Q", data[2:10])[0]
        offset = 10
    if masked:
        if len(data) < offset + 4:
            return None, 0
        mask = data[offset:offset + 4]
        offset += 4
    if len(data) < offset + length:
        return None, 0
    payload = bytearray(data[offset:offset + length])
    if masked:
        payload = bytearray(b ^ mask[i % 4] for i, b in enumerate(payload))
    return bytes(payload), offset + length


async def send_json(writer, data):
    try:
        payload = json.dumps(data)
        writer.write(encode_ws_frame(payload))
    except Exception as e:
        print(f"[WS] Send error: {e}", flush=True)
