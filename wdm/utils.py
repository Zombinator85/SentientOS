"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner(); require_lumos_approval()

import re, time
from typing import Dict


class TokenBucket:
    def __init__(self, rate_per_min: int, burst: int):
        self.rate = rate_per_min
        self.burst = burst
        self.tokens = burst
        self.ts = time.time()

    def allow(self) -> bool:
        now = time.time()
        self.tokens = min(self.burst, self.tokens + (now - self.ts) * (self.rate/60.0))
        self.ts = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True
        return False


def redact(text: str, patterns: list[str]) -> str:
    out = text
    for p in patterns:
        out = re.sub(p, "[REDACTED]", out)
    return out


def build_buckets(cfg: Dict) -> Dict[str, TokenBucket]:
    q = cfg.get("initiation", {})
    per = int(q.get("per_endpoint_quota", 3))
    # Simple minute-scale bucket to keep tests deterministic
    return {"default": TokenBucket(rate_per_min=per, burst=per)}

