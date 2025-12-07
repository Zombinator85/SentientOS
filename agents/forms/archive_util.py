"""Deterministic, in-memory archive helpers for SSA review bundles.

The placeholder encryption keeps artifacts contained to memory without
any file writes. The goal is to gate external persistence behind
explicit approval while ensuring reproducible outputs for testing.
"""
from __future__ import annotations

import base64
import json
from typing import List


def _xor_bytes(payload: bytes, key: int = 0xAA) -> bytes:
    return bytes(b ^ key for b in payload)


def build_encrypted_archive(pdf: bytes, screenshots: List[bytes], log: list) -> bytes:
    """Build a deterministic, in-memory encrypted archive.

    The payload concatenates base64-encoded bytes and the raw execution log
    into a JSON structure and applies a simple XOR-based mask. This is not
    intended for production cryptography but provides deterministic byte
    streams for testing while keeping artifacts in memory only.
    """

    payload = {
        "pdf": base64.b64encode(pdf or b"").decode("utf-8"),
        "screenshots": [base64.b64encode(blob or b"").decode("utf-8") for blob in (screenshots or [])],
        "log": log or [],
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _xor_bytes(serialized)
