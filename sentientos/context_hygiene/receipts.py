from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from sentientos.context_hygiene.context_packet import ContextAssemblyStatus, ContextPacket


DEFAULT_LEDGER_PATH = Path("logs/context_hygiene/context_assembly_receipts.jsonl")


def build_context_assembly_receipt(packet: ContextPacket) -> dict[str, Any]:
    included_ref_counts = {
        "memory": len(packet.included_memory_refs),
        "claim": len(packet.included_claim_refs),
        "evidence": len(packet.included_evidence_refs),
        "stance": len(packet.included_stance_refs),
        "diagnostic": len(packet.included_diagnostic_refs),
        "embodiment": len(packet.included_embodiment_refs),
    }
    return {
        "schema_version": packet.schema_version,
        "receipt_id": str(uuid4()),
        "context_packet_id": packet.context_packet_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "assembly_status": ContextAssemblyStatus.COMPLETE.value,
        "included_ref_counts": included_ref_counts,
        "excluded_ref_counts": {"excluded": len(packet.excluded_refs)},
        "inclusion_reasons": list(packet.inclusion_reasons),
        "exclusion_reasons": list(packet.exclusion_reasons),
        "freshness_status": packet.freshness_status.value,
        "contradiction_status": packet.contradiction_status.value,
        "provenance_complete": packet.provenance_complete,
        "pollution_risk": packet.pollution_risk.value,
        "non_authoritative": True,
        "decision_power": "none",
        "does_not_write_memory": True,
        "does_not_execute_or_route_work": True,
    }


def append_context_assembly_receipt(packet: ContextPacket, ledger_path: str | Path | None = None) -> dict[str, Any]:
    receipt = build_context_assembly_receipt(packet)
    target = Path(ledger_path) if ledger_path else DEFAULT_LEDGER_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(receipt, sort_keys=True) + "\n")
    return receipt
