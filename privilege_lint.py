"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details.

This wrapper invokes :mod:`privilege_lint_cli` after enforcing the
required admin banner. Command usage is logged to the JSONL file
specified by the ``PRIVILEGED_AUDIT_FILE`` environment variable
(default ``logs/privileged_audit.jsonl``). See :doc:`docs/ENVIRONMENT`.
"""
require_admin_banner()
require_lumos_approval()
from __future__ import annotations

from admin_utils import require_admin_banner, require_lumos_approval
import sys

from privilege_lint_cli import main

if __name__ == "__main__":
    sys.exit(main())
