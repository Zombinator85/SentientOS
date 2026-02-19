from __future__ import annotations

from sentientos.forge_index import rebuild_index
from sentientos.forge_status import compute_status

from .context import ForgeContext
from .types import print_json


def handle_status(context: ForgeContext) -> int:
    status = compute_status(context.forge.repo_root)
    print_json({"command": "status", "status": status.to_dict()}, indent=2)
    return 0


def handle_index(context: ForgeContext) -> int:
    payload = rebuild_index(context.forge.repo_root)
    print_json(
        {
            "command": "index",
            "generated_at": payload.get("generated_at"),
            "reports": len(payload.get("latest_reports", [])),
            "dockets": len(payload.get("latest_dockets", [])),
            "receipts": len(payload.get("latest_receipts", [])),
            "queue_pending": len(payload.get("latest_queue", [])),
            "corrupt_count": payload.get("corrupt_count"),
            "audit_dockets": len(payload.get("latest_audit_dockets", [])),
            "audit_strict_status": payload.get("audit_strict_status"),
        },
        indent=2,
    )
    return 0


def handle_quarantines(context: ForgeContext) -> int:
    payload = rebuild_index(context.forge.repo_root)
    print_json({"command": "quarantines", "rows": payload.get("latest_quarantines", [])}, indent=2)
    return 0
