from __future__ import annotations

import shlex

ALLOWED_COMMANDS: set[tuple[str, ...]] = {
    ("python", "scripts/audit_chain_doctor.py", "--repair-index-only"),
    ("python", "scripts/verify_audits.py", "--strict"),
    ("python", "scripts/verify_receipt_chain.py", "--last", "50"),
    ("python", "scripts/verify_receipt_anchors.py", "--last", "10"),
    ("python", "scripts/anchor_receipt_chain.py"),
    ("python", "-m", "sentientos.integrity_snapshot"),
    ("python", "scripts/publish_anchor_witness.py"),
    ("python", "scripts/verify_doctrine_identity.py"),
    ("python", "scripts/emit_stability_doctrine.py"),
}


def normalize_command(command: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in shlex.split(command) if part.strip())


def is_allowlisted(command: str) -> bool:
    return normalize_command(command) in ALLOWED_COMMANDS
