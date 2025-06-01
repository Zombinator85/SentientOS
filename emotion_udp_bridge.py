import json
import socket
from typing import List


class EmotionUDPBridge:
    """Send a 64D emotion vector as UDP JSON packets."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9000) -> None:
        self.addr = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.vector: List[float] = [0.0] * 64

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
