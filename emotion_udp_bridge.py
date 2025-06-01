import json
import socket
from typing import List
import time


class EmotionUDPBridge:
    """Send a 64D emotion vector as UDP JSON packets."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9000) -> None:
        self.addr = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.vector: List[float] = [0.0] * 64
        self.last_ping = 0.0

    def update_vector(self, vector: List[float]) -> None:
        if len(vector) != 64:
            raise ValueError("vector must have 64 elements")
        self.vector = [float(v) for v in vector]
        self.send()

    def send(self) -> None:
        msg = json.dumps({"emotions": self.vector})
        try:
            self.sock.sendto(msg.encode("utf-8"), self.addr)
        except Exception:
            pass
        self._maybe_ping()

    def ping(self) -> None:
        """Send a heartbeat ping."""
        try:
            self.sock.sendto(b"{\"ping\":1}", self.addr)
        except Exception:
            pass

    def _maybe_ping(self) -> None:
        if time.time() - self.last_ping >= 5:
            self.ping()
            self.last_ping = time.time()
