"""
main.py
-------
Tkinter user interface for the P2P Network.

Run:  python main.py

The GUI only talks to P2PNode (p2p_node.py). Network threads never touch
Tkinter widgets directly; they put events into a queue and the GUI thread
reads that queue every 100 ms (Tkinter is not thread-safe).
"""

import os
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, ttk

from p2p_node import P2PNode, human_size, validate_port

# ----------------------------------------------------------------------
# Colour theme
# ----------------------------------------------------------------------
BG = "#EEF1F5"           # window background
CARD = "#FFFFFF"         # section background
TEXT = "#1E293B"         # normal text
MUTED = "#64748B"

ACCENT = "#2F4A6D"       # one standard navy colour for the whole page
HEADER = "#22374F"       # slightly darker shade for the top bar
TINT = "#EEF2F7"         # light tint of the accent
BORDER = "#C6D1DE"
INDIGO = SKY = EMERALD = AMBER = PINK = VIOLET = GREEN = ACCENT
RED = "#DC2626"

LOG_BG = "#0F172A"       # dark log panel so coloured lines stand out
LOG_COLOURS = {
    "success": "#4ADE80",   # green  -> successful actions
    "error": "#F87171",     # red    -> failures / disconnects
    "warning": "#FBBF24",   # yellow -> warnings
    "info": "#93C5FD",      # light blue -> system info
    "incoming": "#67E8F9",  # cyan   -> message received
    "outgoing": "#F0ABFC",  # pink   -> message sent by you
    "time": "#64748B",
}

FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_TITLE = ("Segoe UI", 16, "bold")
FONT_LOG = ("Consolas", 10)


class ColorButton(tk.Label):
    """A flat coloured button that looks the same on Windows, Linux and macOS."""

    def __init__(self, master, text, color, command, width=14):
        super().__init__(master, text=text, bg=color, fg="white", font=FONT_BOLD,
                         padx=10, pady=5, width=width, cursor="hand2")
        self.color = color
        self.hover = self._shade(color, 0.85)
        self.command = command
        self.enabled = True
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", lambda e: self.enabled and self.config(bg=self.hover))
        self.bind("<Leave>", lambda e: self.enabled and self.config(bg=self.color))

    def _click(self, _event):
        if self.enabled:
            self.command()

    def set_enabled(self, enabled):
        self.enabled = enabled
        self.config(bg=self.color if enabled else "#CBD5E1",
                    fg="white" if enabled else "#F1F5F9",
                    cursor="hand2" if enabled else "arrow")

    @staticmethod
    def _shade(hex_color, factor):
        r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
        return "#%02x%02x%02x" % (int(r * factor), int(g * factor), int(b * factor))


def card(parent, title, accent):
    """A white section with a coloured title strip. Returns the inner frame."""
    outer = tk.Frame(parent, bg=CARD, highlightbackground=accent, highlightthickness=2)
    tk.Label(outer, text="  " + title, bg=accent, fg="white", font=FONT_BOLD,
             anchor="w", pady=3).pack(fill="x")
    inner = tk.Frame(outer, bg=CARD, padx=10, pady=8)
    inner.pack(fill="both", expand=True)
    return outer, inner


def label(parent, text, fg=TEXT, font=FONT):
    return tk.Label(parent, text=text, bg=CARD, fg=fg, font=font)


def entry(parent, width, default=""):
    e = tk.Entry(parent, width=width, font=FONT, relief="solid", bd=1,
                 highlightthickness=1, highlightcolor=INDIGO, highlightbackground="#CBD5E1")
    e.insert(0, default)
    return e


class P2PApp:
    def __init__(self, root):
        self.root = root
        self.node = None
        self.events = queue.Queue()
        self.peer_ids = []          # peer_id for each row of the listbox

        root.title("P2P Network")
        root.geometry("1100x760")
        root.minsize(860, 600)
        root.configure(bg=BG)

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("P2P.Horizontal.TProgressbar", troughcolor=TINT,
                        background=VIOLET, bordercolor=TINT, lightcolor=VIOLET, darkcolor=VIOLET)

        self._build_header()
        self._build_my_peer()
        self._build_connect()
        # bottom sections are packed first so they never get cut off
        self._build_status_bar()
        self._build_send_file()
        self._build_send_text()
        self._build_middle()

        self._set_running(False)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(100, self._process_events)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_header(self):
        header = tk.Frame(self.root, bg=HEADER, pady=8)
        header.pack(fill="x")
        tk.Label(header, text="  ⛓ P2P Network", bg=HEADER, fg="white",
                 font=FONT_TITLE).pack(side="left")

    def _build_my_peer(self):
        outer, f = card(self.root, "My Peer", INDIGO)
        outer.pack(fill="x", padx=12, pady=(10, 5))

        label(f, "Name:").grid(row=0, column=0, sticky="w")
        self.name_entry = entry(f, 18, "Tahsin")
        self.name_entry.grid(row=0, column=1, padx=(4, 14))
        label(f, "Port:").grid(row=0, column=2, sticky="w")
        self.port_entry = entry(f, 8, "5000")
        self.port_entry.grid(row=0, column=3, padx=(4, 14))
        self.start_btn = ColorButton(f, "▶ Start Peer", GREEN, self.start_peer)
        self.start_btn.grid(row=0, column=4, padx=4)
        self.stop_btn = ColorButton(f, "■ Stop", RED, self.stop_peer, width=10)
        self.stop_btn.grid(row=0, column=5, padx=4)

        self.peer_info = label(f, "Peer not started", fg=MUTED)
        self.peer_info.grid(row=1, column=0, columnspan=6, sticky="w", pady=(6, 0))
        self.name_entry.bind("<Return>", lambda e: self.start_peer())
        self.port_entry.bind("<Return>", lambda e: self.start_peer())

    def _build_connect(self):
        outer, f = card(self.root, "Connect to Another Peer", SKY)
        outer.pack(fill="x", padx=12, pady=5)
        label(f, "IP:").grid(row=0, column=0, sticky="w")
        self.ip_entry = entry(f, 18, "127.0.0.1")
        self.ip_entry.grid(row=0, column=1, padx=(4, 14))
        label(f, "Port:").grid(row=0, column=2, sticky="w")
        self.rport_entry = entry(f, 8, "5001")
        self.rport_entry.grid(row=0, column=3, padx=(4, 14))
        self.connect_btn = ColorButton(f, "⇄ Connect", SKY, self.connect_peer)
        self.connect_btn.grid(row=0, column=4, padx=4)
        self.rport_entry.bind("<Return>", lambda e: self.connect_peer())

    def _build_middle(self):
        middle = tk.Frame(self.root, bg=BG)
        middle.pack(fill="both", expand=True, padx=12, pady=5)

        # --- Connected peers (left) ---
        outer, f = card(middle, "Connected Peers", EMERALD)
        outer.pack(side="left", fill="y", padx=(0, 6))
        self.peer_count = label(f, "0 peers connected", fg=EMERALD, font=FONT_BOLD)
        self.peer_count.pack(anchor="w")
        list_frame = tk.Frame(f, bg=CARD)
        list_frame.pack(fill="both", expand=True, pady=6)
        self.peer_list = tk.Listbox(list_frame, width=34, font=FONT, activestyle="none",
                                    bg=TINT, fg=TEXT, selectbackground=ACCENT,
                                    selectforeground="white", relief="flat", highlightthickness=1,
                                    highlightbackground=BORDER, exportselection=False)
        sb = tk.Scrollbar(list_frame, command=self.peer_list.yview)
        self.peer_list.config(yscrollcommand=sb.set)
        self.peer_list.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.peer_list.bind("<<ListboxSelect>>", self._on_peer_select)

        # --- Messages / events (right) ---
        outer, f = card(middle, "Messages / Events", AMBER)
        outer.pack(side="left", fill="both", expand=True, padx=(6, 0))

        log_frame = tk.Frame(f, bg=CARD)
        log_frame.pack(fill="both", expand=True)
        self.log = tk.Text(log_frame, font=FONT_LOG, bg=LOG_BG, fg="#E2E8F0", relief="flat",
                           wrap="word", state="disabled", padx=8, pady=6, insertbackground="white")
        lsb = tk.Scrollbar(log_frame, command=self.log.yview)
        self.log.config(yscrollcommand=lsb.set)
        self.log.pack(side="left", fill="both", expand=True)
        lsb.pack(side="right", fill="y")
        for tag, colour in LOG_COLOURS.items():
            self.log.tag_config(tag, foreground=colour)
        self.log.tag_config("success", foreground=LOG_COLOURS["success"], font=("Consolas", 10, "bold"))
        self.log.tag_config("error", foreground=LOG_COLOURS["error"], font=("Consolas", 10, "bold"))

    def _build_send_text(self):
        outer, f = card(self.root, "Send Text", PINK)
        outer.pack(fill="x", side="bottom", padx=12, pady=5)
        self.target_label = label(f, "To: (select a peer from the list)", fg=PINK, font=FONT_BOLD)
        self.target_label.grid(row=0, column=0, sticky="w", columnspan=3)
        self.msg_entry = entry(f, 60)
        self.msg_entry.grid(row=1, column=0, sticky="ew", pady=(4, 0), ipady=3)
        self.send_btn = ColorButton(f, "➤ Send", PINK, self.send_text, width=10)
        self.send_btn.grid(row=1, column=1, padx=(8, 0), pady=(4, 0))
        f.columnconfigure(0, weight=1)
        self.msg_entry.bind("<Return>", lambda e: self.send_text())

    def _build_send_file(self):
        outer, f = card(self.root, "Send File", VIOLET)
        outer.pack(fill="x", side="bottom", padx=12, pady=(5, 8))
        label(f, "Text, image, audio, video, PDF, ZIP, etc.", fg=MUTED).grid(row=0, column=0, sticky="w")
        self.progress = ttk.Progressbar(f, style="P2P.Horizontal.TProgressbar", length=300, maximum=100)
        self.progress.grid(row=0, column=1, sticky="ew", padx=10)
        self.progress_label = label(f, "", fg=VIOLET, font=("Segoe UI", 9))
        self.progress_label.grid(row=1, column=1, sticky="w", padx=10)
        self.file_btn = ColorButton(f, "⇪ Choose File & Send", VIOLET, self.send_file, width=20)
        self.file_btn.grid(row=0, column=3, padx=4)
        f.columnconfigure(1, weight=1)

    def _build_status_bar(self):
        self.status = tk.Label(self.root, text="Ready", bg=HEADER, fg="#E0E7FF",
                               font=("Segoe UI", 9), anchor="w", padx=10, pady=3)
        self.status.pack(fill="x", side="bottom")

    # ------------------------------------------------------------------
    # Thread-safe event handling
    # ------------------------------------------------------------------
    def _node_event(self, level, text):
        self.events.put(("log", level, text))

    def _node_peers_changed(self):
        self.events.put(("peers",))

    def _node_progress(self, direction, peer_name, filename, done, total):
        self.events.put(("progress", direction, peer_name, filename, done, total))

    def _process_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "log":
                    self._write_log(event[1], event[2])
                elif event[0] == "peers":
                    self._refresh_peers()
                elif event[0] == "progress":
                    self._show_progress(*event[1:])
                elif event[0] == "call":
                    event[1]()
        except queue.Empty:
            pass
        self.root.after(100, self._process_events)

    def _write_log(self, level, text):
        prefix = {"success": "[SUCCESS]", "error": "[ERROR]", "warning": "[WARNING]",
                  "info": "[SYSTEM]", "incoming": "[MESSAGE]", "outgoing": "[MESSAGE]"}.get(level, "[SYSTEM]")
        self.log.config(state="normal")
        self.log.insert("end", time.strftime("%H:%M:%S "), "time")
        self.log.insert("end", f"{prefix} {text}\n", level)
        self.log.see("end")
        self.log.config(state="disabled")
        self.status.config(text=text, fg="#FCA5A5" if level == "error" else
                           "#86EFAC" if level == "success" else "#E0E7FF")

    def _show_progress(self, direction, peer_name, filename, done, total):
        percent = 100 if total == 0 else done * 100 / total
        self.progress["value"] = percent
        arrow = "Sending to" if direction == "send" else "Receiving from"
        self.progress_label.config(text=f"{arrow} {peer_name}: {filename} — "
                                        f"{human_size(done)} / {human_size(total)} ({percent:.0f}%)")

    # ------------------------------------------------------------------
    # Peer list
    # ------------------------------------------------------------------
    def _refresh_peers(self):
        selected = self._selected_peer_id()
        peers = self.node.get_peers() if self.node else []
        self.peer_list.delete(0, "end")
        self.peer_ids = []
        for p in peers:
            arrow = "←" if p.direction == "incoming" else "→"
            self.peer_list.insert("end", f" {arrow} {p.label()}")
            self.peer_ids.append(p.peer_id)
        if selected in self.peer_ids:
            self.peer_list.selection_set(self.peer_ids.index(selected))
        elif len(self.peer_ids) == 1:
            self.peer_list.selection_set(0)
        n = len(peers)
        self.peer_count.config(text=f"{n} peer{'s' if n != 1 else ''} connected")
        self._update_target_label()

    def _selected_peer_id(self):
        sel = self.peer_list.curselection()
        if not sel or sel[0] >= len(self.peer_ids):
            return None
        return self.peer_ids[sel[0]]

    def _on_peer_select(self, _event=None):
        self._update_target_label()

    def _update_target_label(self):
        pid = self._selected_peer_id()
        name = None
        if pid and self.node:
            for p in self.node.get_peers():
                if p.peer_id == pid:
                    name = f"{p.peer_name} [{p.peer_id}]"
        self.target_label.config(text=f"To: {name}" if name else "To: (select a peer from the list)")

    def _targets(self):
        """Return the list of peer ids to send to, or show an error."""
        if not self.node:
            self._write_log("error", "Start your peer first")
            return []
        pid = self._selected_peer_id()
        if pid is None:
            self._write_log("error", "Select a peer from the Connected Peers list first")
            return []
        return [pid]

    # ------------------------------------------------------------------
    # Button actions
    # ------------------------------------------------------------------
    def _set_running(self, running):
        self.start_btn.set_enabled(not running)
        self.stop_btn.set_enabled(running)
        self.connect_btn.set_enabled(running)
        self.send_btn.set_enabled(running)
        self.file_btn.set_enabled(running)
        state = "disabled" if running else "normal"
        self.name_entry.config(state=state)
        self.port_entry.config(state=state)

    def start_peer(self):
        if self.node:
            return
        name = self.name_entry.get().strip()
        if not name:
            self._write_log("error", "Please enter a peer name")
            return
        try:
            port = validate_port(self.port_entry.get().strip())
        except ValueError as exc:
            self._write_log("error", str(exc))
            return
        node = P2PNode(name, port, self._node_event, self._node_peers_changed, self._node_progress)
        try:
            node.start()
        except OSError as exc:
            self._write_log("error", f"Could not start peer on port {port}: {exc}")
            return
        self.node = node
        self._set_running(True)
        self.peer_info.config(text=f"{name}  |  ID: {node.peer_id}  |  Port: {port}", fg=INDIGO)
        self.root.title(f"P2P Network — {name} [{node.peer_id}] :{port}")

    def stop_peer(self):
        if not self.node:
            return
        node, self.node = self.node, None
        node.stop()
        self._set_running(False)
        self._refresh_peers()
        self.peer_info.config(text="Peer not started", fg=MUTED)
        self.root.title("P2P Network")

    def connect_peer(self):
        if not self.node:
            self._write_log("error", "Start your peer first")
            return
        ip = self.ip_entry.get().strip()
        port = self.rport_entry.get().strip()
        if not ip:
            self._write_log("error", "Please enter the remote IP address")
            return
        self._write_log("info", f"Connecting to {ip}:{port} ...")
        node = self.node

        def worker():                       # connect() may take a few seconds
            try:
                node.connect(ip, port)
            except Exception as exc:
                self._node_event("error", f"Connection failed: {exc}")

        threading.Thread(target=worker, daemon=True).start()

    def send_text(self):
        text = self.msg_entry.get().strip()
        if not text:
            self._write_log("error", "Message is empty")
            return
        targets = self._targets()
        if not targets:
            return
        for pid in targets:
            try:
                self.node.send_text(pid, text)
            except Exception as exc:
                self._write_log("error", f"Message not sent: {exc}")
        self.msg_entry.delete(0, "end")

    def send_file(self):
        targets = self._targets()
        if not targets:
            return
        path = filedialog.askopenfilename(title="Choose a file to send")
        if not path:
            return
        if not os.path.isfile(path):
            self._write_log("error", f"File does not exist: {path}")
            return
        node = self.node
        self.progress["value"] = 0

        def worker():                       # large files: don't freeze the GUI
            for pid in targets:
                try:
                    node.send_file(pid, path)
                except Exception as exc:
                    self._node_event("error", f"File not sent: {exc}")

        threading.Thread(target=worker, daemon=True).start()

    def on_close(self):
        if self.node:
            self.node.stop()
        self.root.destroy()


def main():
    root = tk.Tk()
    P2PApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
