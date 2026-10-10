"""
protocol.py
-----------
Application-level protocol for the P2P network.

TCP is a byte stream: it does NOT keep message boundaries. So every
JSON control message is "framed" like this:

    +----------------+----------------------+
    | 4-byte length  |   JSON payload       |
    +----------------+----------------------+

The length is an unsigned 32-bit big-endian integer (struct format "!I").
The receiver first reads exactly 4 bytes, then reads exactly `length` bytes.

Message types used:
    hello      -> sent by the peer that opens the connection (handshake)
    hello_ack  -> reply to hello (handshake complete)
    text       -> a chat message
    file       -> file metadata; followed IMMEDIATELY by `filesize` raw bytes
    bye        -> polite disconnect notice
"""

import json
import struct

HEADER_SIZE = 4                    # 4-byte length prefix
HEADER_FORMAT = "!I"               # network byte order, unsigned int
MAX_MESSAGE_SIZE = 10 * 1024 * 1024  # safety limit for one JSON message (10 MB)
CHUNK_SIZE = 64 * 1024             # 64 KB chunks for file transfer

# Message type constants
HELLO = "hello"
HELLO_ACK = "hello_ack"
TEXT = "text"
FILE = "file"
BYE = "bye"


class ProtocolError(Exception):
    """Raised when the received data does not follow the protocol."""


class ConnectionClosed(Exception):
    """Raised when the remote peer closes the connection."""


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------
def recv_exact(sock, num_bytes):
    """
    Read EXACTLY num_bytes from the socket.

    One recv() call may return fewer bytes than requested, so we loop
    until we have collected everything.
    """
    data = bytearray()
    while len(data) < num_bytes:
        chunk = sock.recv(num_bytes - len(data))
        if not chunk:                       # empty bytes => peer closed
            raise ConnectionClosed("Peer closed the connection")
        data.extend(chunk)
    return bytes(data)


# ---------------------------------------------------------------------------
# Encode / decode
# ---------------------------------------------------------------------------
def encode_message(message: dict) -> bytes:
    """dict -> [4-byte length][JSON bytes]"""
    payload = json.dumps(message).encode("utf-8")
    if len(payload) > MAX_MESSAGE_SIZE:
        raise ProtocolError("Message too large")
    return struct.pack(HEADER_FORMAT, len(payload)) + payload


def decode_payload(payload: bytes) -> dict:
    """JSON bytes -> dict"""
    try:
        message = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"Invalid JSON message: {exc}") from exc
    if not isinstance(message, dict) or "type" not in message:
        raise ProtocolError("Message has no 'type' field")
    return message


def send_message(sock, message: dict):
    """Frame and send one JSON message."""
    sock.sendall(encode_message(message))


def receive_message(sock) -> dict:
    """Receive one framed JSON message."""
    header = recv_exact(sock, HEADER_SIZE)
    (length,) = struct.unpack(HEADER_FORMAT, header)
    if length == 0 or length > MAX_MESSAGE_SIZE:
        raise ProtocolError(f"Invalid message length: {length}")
    payload = recv_exact(sock, length)
    return decode_payload(payload)


# ---------------------------------------------------------------------------
# Message builders (keep the message format in ONE place)
# ---------------------------------------------------------------------------
def make_hello(peer_id, peer_name, port):
    return {"type": HELLO, "peer_id": peer_id, "peer_name": peer_name, "port": port}


def make_hello_ack(peer_id, peer_name, port):
    return {"type": HELLO_ACK, "peer_id": peer_id, "peer_name": peer_name, "port": port}


def make_text(sender_id, sender_name, text):
    return {"type": TEXT, "sender_id": sender_id, "sender_name": sender_name, "message": text}


def make_file(sender_id, sender_name, filename, filesize):
    return {
        "type": FILE,
        "sender_id": sender_id,
        "sender_name": sender_name,
        "filename": filename,
        "filesize": filesize,
    }


def make_bye(sender_id, sender_name):
    return {"type": BYE, "sender_id": sender_id, "sender_name": sender_name}
