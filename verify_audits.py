"""Compatibility wrapper for sentientos.verify_audits stable module path."""

from __future__ import annotations

from sentientos.audit_tools import verify_audits_main as main


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
