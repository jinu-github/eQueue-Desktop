"""Persistent WebSocket connection to the server's /ws endpoint, running
on a background thread so incoming push messages don't block the UI.
Auto-reconnects with a short backoff if the connection drops (e.g. the
server restarts) rather than giving up permanently.

Usage:
    self._ws = QueueWebSocketClient(self.api.base_url)
    self._ws.message_received.connect(self._on_ws_message)
    self._ws.start()
    ...
    self._ws.stop()  # call on window close/logout, or it leaks a thread
"""
import json
import time
from PyQt6.QtCore import QThread, pyqtSignal
import websocket


def _to_ws_url(http_base_url: str) -> str:
    url = http_base_url.rstrip("/")
    if url.startswith("https://"):
        url = "wss://" + url[len("https://"):]
    elif url.startswith("http://"):
        url = "ws://" + url[len("http://"):]
    return url + "/ws"


class QueueWebSocketClient(QThread):
    message_received = pyqtSignal(dict)
    connected = pyqtSignal()
    disconnected = pyqtSignal()

    def __init__(self, http_base_url: str, parent=None):
        super().__init__(parent)
        self._url = _to_ws_url(http_base_url)
        self._should_run = True
        self._ws_app = None

    def run(self):
        backoff = 1
        while self._should_run:
            try:
                self._ws_app = websocket.WebSocketApp(
                    self._url,
                    on_open=lambda ws: self.connected.emit(),
                    on_message=self._handle_message,
                    on_close=lambda ws, *a: self.disconnected.emit(),
                    on_error=lambda ws, err: None,
                )
                backoff = 1  # connected fine at least once - reset the backoff
                self._ws_app.run_forever(ping_interval=20, ping_timeout=10)
            except Exception:
                pass

            if not self._should_run:
                break

            # Sleep in small slices instead of one long time.sleep(backoff),
            # so stop() can interrupt a reconnect wait almost immediately
            # instead of having to wait out the full backoff period.
            slept = 0.0
            while slept < backoff and self._should_run:
                time.sleep(0.2)
                slept += 0.2
            backoff = min(backoff * 2, 30)  # cap reconnect wait at 30s

    def _handle_message(self, ws, message):
        try:
            data = json.loads(message)
        except (json.JSONDecodeError, TypeError):
            return
        self.message_received.emit(data)

    def stop(self):
        self._should_run = False
        if self._ws_app:
            self._ws_app.close()
        self.wait(5000)