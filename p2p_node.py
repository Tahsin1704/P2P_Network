"""
p2p_node.py
-----------
The networking layer of one peer.

Every peer = TCP Server + TCP Client
    * Server role : a listening socket accepts incoming connections.
    * Client role : connect() opens outgoing connections to other peers.

Each connection (incoming or outgoing) is handled by its own thread, so
the peer can talk to many peers at the same time while still accepting
new ones.

The node never touches the GUI directly. It reports everything through
callbacks:
    on_event(level, text)          level: info | success | error | incoming | outgoing | warning
    on_peers_changed()             connected-peer list changed
    on_progress(direction, peer_name, filename, done, total)
"""

import ipaddress
import os
import socket
import threading
import uuid

import protocol

DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
CONNECT_TIMEOUT = 5      # seconds to wait for connect()
HANDSHAKE_TIMEOUT = 10   # seconds to wait for hello / hello_ack


class PeerConnection:
    """Information about one connected remote peer."""

    def __init__(self, sock, address, peer_id, peer_name, listen_port, direction):
        self.sock = sock
        self.address = address          # (ip, port) of the TCP connection
        self.peer_id = peer_id
        self.peer_name = peer_name
        self.listen_port = listen_port  # port the remote peer listens on
        self.direction = direction      # "incoming" or "outgoing"
        # One lock per connection so a text message can never be inserted
        # in the middle of the raw bytes of a file that is being sent.
        self.send_lock = threading.Lock()

    def label(self):
        return f"{self.peer_name} [{self.peer_id}] {self.address[0]}:{self.listen_port}"


class P2PNode:
    def __init__(self, name, port, on_event=None, on_peers_changed=None, on_progress=None):
        self.name = name
        self.port = port
        self.peer_id = uuid.uuid4().hex[:8]       # short unique id, e.g. a83f21c4

        self.on_event = on_event or (lambda level, text: print(f"[{level.upper()}] {text}"))
        self.on_peers_changed = on_peers_changed or (lambda: None)
        self.on_progress = on_progress or (lambda *args: None)

        self.server_socket = None
        self.running = False
        self.peers = {}                     # peer_id -> PeerConnection
        self.peers_lock = threading.Lock()

        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    # ------------------------------------------------------------------
    # Server role
    # ------------------------------------------------------------------
    def start(self):
        """socket() -> bind() -> listen(), then accept() in a background thread."""
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server_socket.bind(("0.0.0.0", self.port))
            self.server_socket.listen()
        except OSError:
            self.server_socket.close()
            self.server_socket = None
            raise
        self.running = True
        threading.Thread(target=self._accept_loop, daemon=True).start()
        self.on_event("success", f"Peer started: {self.name} [{self.peer_id}] listening on port {self.port}")

    def _accept_loop(self):
        while self.running:
            try:
                conn, address = self.server_socket.accept()
            except OSError:
                break                       # server socket closed by stop()
            # one new thread per incoming connection
            threading.Thread(target=self._handle_incoming, args=(conn, address), daemon=True).start()

    def _handle_incoming(self, conn, address):
        """Incoming side of the handshake: receive HELLO, reply HELLO_ACK."""
        try:
            conn.settimeout(HANDSHAKE_TIMEOUT)
            hello = protocol.receive_message(conn)
            if hello.get("type") != protocol.HELLO:
                raise protocol.ProtocolError("Expected HELLO message")
            protocol.send_message(conn, protocol.make_hello_ack(self.peer_id, self.name, self.port))
            conn.settimeout(None)
        except Exception as exc:
            self.on_event("error", f"Handshake failed with {address[0]}:{address[1]}: {exc}")
            conn.close()
            return

        peer = PeerConnection(conn, address, hello.get("peer_id", "?"), hello.get("peer_name", "Unknown"),
                              hello.get("port", address[1]), "incoming")
        if not self._register_peer(peer):
            return
        self.on_event("success", f"{peer.peer_name} connected to you ({address[0]}:{peer.listen_port})")
        self._receive_loop(peer)

    # ------------------------------------------------------------------
    # Client role
    # ------------------------------------------------------------------
    def connect(self, ip, port):
        """socket() -> connect() -> send HELLO -> wait HELLO_ACK. Raises on failure."""
        if not self.running:
            raise RuntimeError("Start your peer first")
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            # allow host names such as "localhost"
            try:
                ip = socket.gethostbyname(ip)
            except socket.gaierror:
                raise ValueError(f"Invalid IP address: {ip}")
        port = validate_port(port)
        if port == self.port and (ip.startswith("127.") or ip in self._local_ips()):
            raise ValueError("You cannot connect to yourself")

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(CONNECT_TIMEOUT)
        try:
            sock.connect((ip, port))
            sock.settimeout(HANDSHAKE_TIMEOUT)
            protocol.send_message(sock, protocol.make_hello(self.peer_id, self.name, self.port))
            ack = protocol.receive_message(sock)
            if ack.get("type") != protocol.HELLO_ACK:
                raise protocol.ProtocolError("Expected HELLO_ACK message")
            sock.settimeout(None)
        except socket.timeout:
            sock.close()
            raise ConnectionError("Connection timed out")
        except ConnectionRefusedError:
            sock.close()
            raise ConnectionError("Connection refused (is the peer running?)")
        except Exception:
            sock.close()
            raise

        peer = PeerConnection(sock, (ip, port), ack.get("peer_id", "?"), ack.get("peer_name", "Unknown"),
                              ack.get("port", port), "outgoing")
        if not self._register_peer(peer):
            raise ConnectionError(f"Already connected to {peer.peer_name}")
        self.on_event("success", f"Connected to {peer.peer_name} [{peer.peer_id}] ({ip}:{port})")
        threading.Thread(target=self._receive_loop, args=(peer,), daemon=True).start()
        return peer

    # ------------------------------------------------------------------
    # Peer bookkeeping
    # ------------------------------------------------------------------
    def _register_peer(self, peer):
        with self.peers_lock:
            if peer.peer_id == self.peer_id or peer.peer_id in self.peers:
                duplicate = True
            else:
                self.peers[peer.peer_id] = peer
                duplicate = False
        if duplicate:
            self.on_event("warning", f"Duplicate connection with {peer.peer_name} ignored")
            try:
                peer.sock.close()
            except OSError:
                pass
            return False
        self.on_peers_changed()
        return True

    def _remove_peer(self, peer, reason):
        with self.peers_lock:
            removed = self.peers.pop(peer.peer_id, None) is not None
        try:
            peer.sock.close()
        except OSError:
            pass
        if removed and self.running:
            self.on_event("error", f"{peer.peer_name} disconnected ({reason})")
            self.on_peers_changed()

    def get_peers(self):
        with self.peers_lock:
            return list(self.peers.values())

    # ------------------------------------------------------------------
    # Receiving (one thread per connection)
    # ------------------------------------------------------------------
    def _receive_loop(self, peer):
        try:
            while self.running:
                message = protocol.receive_message(peer.sock)
                mtype = message.get("type")
                if mtype == protocol.TEXT:
                    self.on_event("incoming", f"{peer.peer_name} -> You: {message.get('message', '')}")
                elif mtype == protocol.FILE:
                    self._receive_file(peer, message)
                elif mtype == protocol.BYE:
                    self._remove_peer(peer, "left the network")
                    return
                else:
                    self.on_event("warning", f"Unknown message type from {peer.peer_name}: {mtype}")
        except protocol.ConnectionClosed:
            self._remove_peer(peer, "connection closed")
        except (OSError, protocol.ProtocolError) as exc:
            self._remove_peer(peer, str(exc) if self.running else "peer stopped")

    def _receive_file(self, peer, meta):
        """Metadata already received -> now read EXACTLY `filesize` raw bytes."""
        filename = safe_filename(meta.get("filename", "file.bin"))
        filesize = meta.get("filesize")
        if not isinstance(filesize, int) or filesize < 0:
            # we cannot know where the file ends, so the stream is unusable
            raise protocol.ProtocolError(f"Invalid file size: {filesize}")

        path = unique_path(os.path.join(DOWNLOAD_DIR, filename))
        self.on_event("info", f"Receiving '{filename}' ({human_size(filesize)}) from {peer.peer_name}...")
        received = 0
        try:
            with open(path, "wb") as f:
                while received < filesize:
                    chunk = peer.sock.recv(min(protocol.CHUNK_SIZE, filesize - received))
                    if not chunk:
                        raise protocol.ConnectionClosed("Peer closed during file transfer")
                    f.write(chunk)
                    received += len(chunk)
                    self.on_progress("recv", peer.peer_name, filename, received, filesize)
        except Exception:
            # delete the incomplete file
            try:
                os.remove(path)
            except OSError:
                pass
            self.on_event("error", f"File '{filename}' from {peer.peer_name} was not completed")
            raise
        self.on_event("success", f"{peer.peer_name} -> You: File received: {os.path.basename(path)} "
                                 f"({human_size(filesize)}) saved to downloads/")

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------
    def _get_peer(self, peer_id):
        with self.peers_lock:
            peer = self.peers.get(peer_id)
        if peer is None:
            raise ValueError("Selected peer is not connected")
        return peer

    def send_text(self, peer_id, text):
        peer = self._get_peer(peer_id)
        message = protocol.make_text(self.peer_id, self.name, text)
        try:
            with peer.send_lock:
                protocol.send_message(peer.sock, message)
        except OSError as exc:
            self._remove_peer(peer, str(exc))
            raise ConnectionError(f"Could not send to {peer.peer_name}: {exc}")
        self.on_event("outgoing", f"You -> {peer.peer_name}: {text}")

    def send_file(self, peer_id, file_path):
        """Send metadata first, then raw bytes in 64 KB chunks. Blocking: call from a thread."""
        peer = self._get_peer(peer_id)
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"File does not exist: {file_path}")
        filename = os.path.basename(file_path)
        filesize = os.path.getsize(file_path)
        meta = protocol.make_file(self.peer_id, self.name, filename, filesize)

        self.on_event("info", f"Sending '{filename}' ({human_size(filesize)}) to {peer.peer_name}...")
        sent = 0
        try:
            with peer.send_lock, open(file_path, "rb") as f:
                protocol.send_message(peer.sock, meta)        # 1) metadata
                while True:                                     # 2) raw bytes
                    chunk = f.read(protocol.CHUNK_SIZE)
                    if not chunk:
                        break
                    peer.sock.sendall(chunk)
                    sent += len(chunk)
                    self.on_progress("send", peer.peer_name, filename, sent, filesize)
        except OSError as exc:
            if isinstance(exc, (FileNotFoundError, PermissionError)) and sent == 0:
                raise
            self._remove_peer(peer, str(exc))
            raise ConnectionError(f"File transfer to {peer.peer_name} failed: {exc}")
        if sent != filesize:
            raise IOError("File changed while sending")
        self.on_event("success", f"You -> {peer.peer_name}: File sent: {filename} ({human_size(filesize)})")

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------
    def stop(self):
        self.running = False
        for peer in self.get_peers():
            try:
                with peer.send_lock:
                    protocol.send_message(peer.sock, protocol.make_bye(self.peer_id, self.name))
            except OSError:
                pass
            try:
                peer.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            peer.sock.close()
        with self.peers_lock:
            self.peers.clear()
        if self.server_socket:
            try:
                self.server_socket.close()
            except OSError:
                pass
            self.server_socket = None
        self.on_peers_changed()
        self.on_event("warning", "Peer stopped. All connections closed.")

    @staticmethod
    def _local_ips():
        ips = set()
        try:
            ips.update(socket.gethostbyname_ex(socket.gethostname())[2])
        except OSError:
            pass
        return ips


# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------
def validate_port(port):
    try:
        port = int(port)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid port: {port}")
    if not 1 <= port <= 65535:
        raise ValueError(f"Invalid port: {port} (must be 1-65535)")
    return port


def safe_filename(name):
    """Strip any directory part so a peer cannot write outside downloads/."""
    name = os.path.basename(str(name).replace("\\", "/")).strip()
    return name if name not in ("", ".", "..") else "file.bin"


def unique_path(path):
    """photo.jpg -> photo (1).jpg if photo.jpg already exists."""
    base, ext = os.path.splitext(path)
    counter = 1
    while os.path.exists(path):
        path = f"{base} ({counter}){ext}"
        counter += 1
    return path


def get_local_ip():
    """Best-guess LAN IP of this computer (no data is actually sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def human_size(num):
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024
