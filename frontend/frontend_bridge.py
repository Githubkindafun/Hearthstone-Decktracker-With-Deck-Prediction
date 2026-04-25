from __future__ import annotations

import json
import socketserver
import threading
from typing import Callable, Optional


class _ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class _ClientHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        server = self.server
        server.bridge._register(self.request)
        buf = ""
        try:
            while True:
                data = self.request.recv(4096)
                if not data:
                    break
                buf += data.decode("utf-8", errors="replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    server.bridge._handle_message(msg, self.request)
        finally:
            server.bridge._unregister(self.request)


class FrontendBridge:
    def __init__(self, host: str, port: int, on_message: Callable[[dict, object], None]):
        self._host = host
        self._port = port
        self._on_message = on_message
        self._clients: set[object] = set()
        self._lock = threading.Lock()
        self._server: Optional[_ThreadedTCPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        server = _ThreadedTCPServer((self._host, self._port), _ClientHandler)
        server.bridge = self
        self._server = server
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self._thread = thread

    def stop(self) -> None:
        if not self._server:
            return
        self._server.shutdown()
        self._server.server_close()
        self._server = None

    def send(self, payload: dict, client: Optional[object] = None) -> None:
        line = json.dumps(payload, ensure_ascii=True) + "\n"
        data = line.encode("utf-8")
        targets = [client] if client is not None else self._snapshot_clients()
        for sock in targets:
            try:
                sock.sendall(data)
            except Exception:
                self._unregister(sock)

    def _snapshot_clients(self) -> list[object]:
        with self._lock:
            return list(self._clients)

    def _register(self, sock: object) -> None:
        with self._lock:
            self._clients.add(sock)
        print("[bridge] client_connected")

    def _unregister(self, sock: object) -> None:
        with self._lock:
            self._clients.discard(sock)
        print("[bridge] client_disconnected")

    def _handle_message(self, payload: dict, client: object) -> None:
        msg_type = payload.get("type")
        print(f"[bridge] recv type={msg_type}")
        try:
            self._on_message(payload, client)
        except Exception:
            pass
