"""Stage-4 OracleRelay execution wrapper.

Provides a minimal, permission-gated interface around an injected relay
object. All operations are in-memory only and intentionally avoid file
writes or persistence to keep the execution layer deterministic and PII-
free.
"""
from __future__ import annotations


class OracleSession:
    def __init__(self, relay, approved: bool):
        self.relay = relay
        self.approved = approved

    def require_approval(self):
        return self.approved

    def navigate(self, url: str) -> dict:
        if not self.approved:
            return {"status": "denied", "reason": "approval_required"}
        result = self.relay.goto(url)
        return {"status": "navigated", "url": url, "raw": result}

    def fill(self, selector: str, value: str) -> dict:
        if not self.approved:
            return {"status": "denied", "reason": "approval_required"}
        result = self.relay.type(selector, value)
        return {"status": "filled", "selector": selector, "value": value}

    def click(self, selector: str) -> dict:
        if not self.approved:
            return {"status": "denied", "reason": "approval_required"}
        result = self.relay.click(selector)
        return {"status": "clicked", "selector": selector}

    def screenshot(self) -> dict:
        if not self.approved:
            return {"status": "denied", "reason": "approval_required"}
        image_bytes = self.relay.screenshot()
        return {"status": "screenshot", "bytes": image_bytes}
