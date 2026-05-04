from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .claim_ledger import DEFAULT_CLAIM_LEDGER
from .evidence_diagnostic import build_evidence_stability_diagnostic
from .evidence_ledger import DEFAULT_EVIDENCE_LEDGER
from .stance_receipts import DEFAULT_CONTRADICTION_LEDGER, DEFAULT_STANCE_LEDGER

SCHEMA_VERSION = "phase58.truth_log_fed_diagnostic.v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_truth_ledger_paths() -> dict[str, Path]:
    return {
        "evidence": Path(DEFAULT_EVIDENCE_LEDGER),
        "claim": Path(DEFAULT_CLAIM_LEDGER),
        "stance": Path(DEFAULT_STANCE_LEDGER),
        "contradiction": Path(DEFAULT_CONTRADICTION_LEDGER),
    }


def _read_jsonl_safe(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    if not path.exists():
        return [], [f"missing:{path}"]
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for idx, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"malformed:{path}:{idx}")
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows, errors


def load_truth_records_for_diagnostic(*, ledger_paths: Mapping[str, Path] | None = None) -> dict[str, Any]:
    paths = dict(default_truth_ledger_paths())
    if ledger_paths:
        for key, value in ledger_paths.items():
            paths[str(key)] = Path(value)
    out: dict[str, Any] = {"records": {}, "errors": [], "paths": paths}
    for key in ("evidence", "claim", "stance", "contradiction"):
        rows, errs = _read_jsonl_safe(Path(paths[key]))
        out["records"][f"{key}_receipts"] = rows
        out["errors"].extend(errs)
    out["status"] = "ok" if not out["errors"] else "degraded"
    return out


def summarize_log_fed_truth_state(*, loaded_truth_records: Mapping[str, Any]) -> dict[str, Any]:
    records = dict(loaded_truth_records.get("records") or {})
    return {
        "status": str(loaded_truth_records.get("status") or "unknown"),
        "truth_records_loaded": {
            "evidence_receipts": len(list(records.get("evidence_receipts") or [])),
            "claim_receipts": len(list(records.get("claim_receipts") or [])),
            "stance_receipts": len(list(records.get("stance_receipts") or [])),
            "contradiction_receipts": len(list(records.get("contradiction_receipts") or [])),
        },
        "truth_records_load_errors": list(loaded_truth_records.get("errors") or []),
    }


def build_log_fed_evidence_stability_diagnostic(*, topic_id: str | None = None, ledger_paths: Mapping[str, Path] | None = None) -> dict[str, Any]:
    loaded = load_truth_records_for_diagnostic(ledger_paths=ledger_paths)
    records = loaded["records"]
    diagnostic = build_evidence_stability_diagnostic(
        claim_receipts=records.get("claim_receipts", []),
        evidence_receipts=records.get("evidence_receipts", []),
        stance_receipts=records.get("stance_receipts", []),
        contradiction_receipts=records.get("contradiction_receipts", []),
        topic_id=topic_id,
    )
    summary = summarize_log_fed_truth_state(loaded_truth_records=loaded)
    return {
        "schema_version": SCHEMA_VERSION,
        "log_fed_diagnostic_id": "lfd_" + hashlib.sha256(f"{topic_id or 'none'}|{summary['status']}|{summary['truth_records_loaded']}".encode("utf-8")).hexdigest()[:24],
        "generated_at": _utc_now(),
        "topic_id": topic_id,
        "diagnostic": deepcopy(diagnostic),
        **summary,
        "non_authoritative": True,
        "decision_power": "none",
        "does_not_write_memory": True,
        "does_not_admit_work": True,
        "does_not_execute_or_route_work": True,
        "does_not_trigger_feedback": True,
    }


def truth_log_fed_diagnostic_ref(record: Mapping[str, Any]) -> str:
    return f"truth_log_fed_diagnostic:{record['log_fed_diagnostic_id']}"
