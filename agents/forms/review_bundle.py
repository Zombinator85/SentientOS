"""Stage-6 review bundle assembly with default redaction.

The SSAReviewBundle consolidates execution artifacts into a deterministic
structure for human review. All PII is redacted by default, and any
archival output requires explicit approval before materializing bytes.
"""
from __future__ import annotations

from typing import Any, Dict, List

from agents.forms.archive_util import build_encrypted_archive


def redact_dict(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively redact string leaves within a dictionary structure."""

    def _redact(value: Any):
        if isinstance(value, str):
            return "***"
        if isinstance(value, dict):
            return {k: _redact(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_redact(item) for item in value]
        if isinstance(value, tuple):
            return tuple(_redact(item) for item in value)
        return value

    return _redact(obj)


def redact_log(log: List[dict]) -> List[dict]:
    """Redact sensitive log fields while preserving page names."""

    def _scrub(node: Any) -> Any:
        if isinstance(node, dict):
            redacted: Dict[str, Any] = {}
            for key, value in node.items():
                if key == "page":
                    redacted[key] = value
                    continue
                if key in {"selector", "value", "bytes"}:
                    redacted[key] = "***"
                    continue
                if isinstance(value, (bytes, bytearray)):
                    redacted[key] = "***"
                    continue
                redacted[key] = _scrub(value)
            return redacted
        if isinstance(node, list):
            return [_scrub(item) for item in node]
        if isinstance(node, tuple):
            return tuple(_scrub(item) for item in node)
        return node

    return _scrub(log)


class SSAReviewBundle:
    def __init__(self, execution_log: list, screenshot_bytes: List[bytes], pdf_bytes: bytes, profile: Dict[str, Any]):
        self.execution_log = execution_log
        self.screenshot_bytes = screenshot_bytes
        self.pdf_bytes = pdf_bytes
        self.profile = profile

    def redacted_profile(self) -> dict:
        return redact_dict(self.profile)

    def as_dict(self) -> dict:
        return {
            "execution_log": redact_log(self.execution_log),
            "screenshots": ["<bytes>" for _ in self.screenshot_bytes],
            "prefilled_pdf": "<bytes>",
            "profile": self.redacted_profile(),
        }

    def as_archive(self, approved: bool) -> dict:
        if not approved:
            return {"status": "approval_required"}

        archive_bytes = build_encrypted_archive(pdf=self.pdf_bytes, screenshots=self.screenshot_bytes, log=self.execution_log)

        return {
            "status": "archive_ready",
            "bytes": archive_bytes,
        }
