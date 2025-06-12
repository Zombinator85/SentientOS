"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
import json
import socket
from typing import Dict


def _map_expression(vector: Dict[str, float]) -> str:
    if vector.get("Joy", 0) > 0.5 or vector.get("Love", 0) > 0.5:
        return "smile"
    if vector.get("Sadness", 0) > 0.5 or vector.get("Grief", 0) > 0.5:
        return "frown"
    if vector.get("Surprise (positive)", 0) > 0.5 or vector.get("Astonishment", 0) > 0.5:
        return "surprised"
    if vector.get("Anger", 0) > 0.5 or vector.get("Rage", 0) > 0.5:
        return "angry"
    return "neutral"


def send_expression(vector: Dict[str, float], host: str = "127.0.0.1", port: int = 9100) -> str:
    exp = _map_expression(vector)
    msg = json.dumps({"expression": exp})
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.sendto(msg.encode("utf-8"), (host, port))
    except Exception:
        pass
    return exp
