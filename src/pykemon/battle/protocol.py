"""
Length-prefixed JSON protocol over TCP.

All messages are framed as:
    4 bytes (big-endian unsigned int) = payload length
    N bytes = UTF-8 JSON payload
"""

import json
import socket


def _recvall(sock: socket.socket, n: int) -> bytes:
    """Read exactly n bytes from socket, handling partial reads."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Socket closed before all bytes were received.")
        buf += chunk
    return buf


def send(sock: socket.socket, msg: dict) -> None:
    """Serialize msg to JSON and send with 4-byte length prefix."""
    payload = json.dumps(msg).encode("utf-8")
    sock.sendall(len(payload).to_bytes(4, "big") + payload)


def recv(sock: socket.socket) -> dict:
    """Read a length-prefixed JSON message and return the parsed dict."""
    raw_len = _recvall(sock, 4)
    length = int.from_bytes(raw_len, "big")
    payload = _recvall(sock, length)
    return json.loads(payload)
