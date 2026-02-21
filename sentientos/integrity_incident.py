from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

INCIDENTS_DIR = Path("glow/forge/incidents")
INCIDENTS_FEED_PATH = Path("pulse/integrity_incidents.jsonl")


@dataclass(slots=True)
class Incident:
    schema_version: int
    incident_id: str
    created_at: str
    severity: str
    triggers: list[str]
    enforcement_mode: str
    context: dict[str, object]
    evidence_paths: list[str]
    suggested_actions: list[str]
    governance_trace_id: str | None = None
    remediation_pack_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["triggers"] = list(self.triggers)
        payload["evidence_paths"] = sorted({path for path in self.evidence_paths if path})
        payload["suggested_actions"] = list(self.suggested_actions)
        payload["context"] = _sorted_context(self.context)
        return payload


def build_incident(
    *,
    triggers: list[str],
    enforcement_mode: str,
    severity: str,
    context: dict[str, object] | None = None,
    evidence_paths: list[str] | None = None,
    suggested_actions: list[str] | None = None,
    created_at: str | None = None,
    governance_trace_id: str | None = None,
    remediation_pack_id: str | None = None,
) -> Incident:
    created = created_at or _iso_now()
    normalized_triggers = sorted({item for item in triggers if item})
    normalized_context = _sorted_context(context or {})
    normalized_evidence = sorted({path for path in (evidence_paths or []) if path})
    normalized_actions = list(suggested_actions or [])

    incident_hash = hashlib.sha256(
        json.dumps(
            {
                "created_at": created,
                "enforcement_mode": enforcement_mode,
                "severity": severity,
                "triggers": normalized_triggers,
                "context": normalized_context,
                "evidence_paths": normalized_evidence,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:8]
    incident_id = f"{created}_{incident_hash}"
    return Incident(
        schema_version=1,
        incident_id=incident_id,
        created_at=created,
        severity=severity,
        triggers=normalized_triggers,
        enforcement_mode=enforcement_mode,
        context=normalized_context,
        evidence_paths=normalized_evidence,
        suggested_actions=normalized_actions,
        governance_trace_id=governance_trace_id,
        remediation_pack_id=remediation_pack_id,
    )


def write_incident(repo_root: Path, incident: Incident, *, quarantine_activated: bool = False) -> Path:
    root = repo_root.resolve()
    incident_path = root / INCIDENTS_DIR / f"incident_{_safe_timestamp(incident.created_at)}_{_incident_short_hash(incident.incident_id)}.json"
    incident_path.parent.mkdir(parents=True, exist_ok=True)
    incident_path.write_text(json.dumps(incident.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    append_incident_feed(root, incident, incident_path, quarantine_activated=quarantine_activated)
    return incident_path


def append_incident_feed(repo_root: Path, incident: Incident, incident_path: Path, *, quarantine_activated: bool = False) -> None:
    row = {
        "schema_version": 1,
        "incident_id": incident.incident_id,
        "created_at": incident.created_at,
        "severity": incident.severity,
        "enforcement_mode": incident.enforcement_mode,
        "quarantine_activated": quarantine_activated,
        "triggers": incident.triggers,
        "path": str(incident_path.relative_to(repo_root.resolve())),
        "governance_trace_id": incident.governance_trace_id,
        "remediation_pack_id": incident.remediation_pack_id,
    }
    target = repo_root.resolve() / INCIDENTS_FEED_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def build_base_context(repo_root: Path) -> dict[str, object]:
    root = repo_root.resolve()
    return {
        "head_sha": _head_sha(root),
        "expected_bundle_sha256": _expected_bundle_sha(root),
        "local_bundle_sha256": _local_bundle_sha(root),
        "last_receipt_hash": _last_receipt_hash(root),
        "last_anchor_id": _anchor_field(root, "anchor_id"),
        "last_anchor_tip": _anchor_field(root, "receipt_chain_tip_hash"),
        "receipts_index_sha256": _sha256_file(root / "glow/forge/receipts/receipts_index.jsonl"),
        "witness_last_status": _load_json(root / "glow/federation/anchor_witness_status.json"),
    }


def _sorted_context(value: dict[str, object]) -> dict[str, object]:
    normalized = json.loads(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str))
    return normalized if isinstance(normalized, dict) else {}


def _head_sha(repo_root: Path) -> str | None:
    completed = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value or None


def _expected_bundle_sha(repo_root: Path) -> str | None:
    from sentientos.doctrine_identity import expected_bundle_sha256_from_receipts

    return expected_bundle_sha256_from_receipts(repo_root)


def _local_bundle_sha(repo_root: Path) -> str | None:
    from sentientos.doctrine_identity import local_doctrine_identity

    value = local_doctrine_identity(repo_root).bundle_sha256
    return value or None


def _last_receipt_hash(repo_root: Path) -> str | None:
    from sentientos.receipt_chain import latest_receipt_hash

    return latest_receipt_hash(repo_root)


def _anchor_field(repo_root: Path, field: str) -> str | None:
    anchors = sorted((repo_root / "glow/forge/receipts/anchors").glob("anchor_*.json"), key=lambda item: item.name)
    if not anchors:
        return None
    payload = _load_json(anchors[-1])
    value = payload.get(field)
    return value if isinstance(value, str) and value else None


def _sha256_file(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return hashlib.sha256(data).hexdigest()


def _load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _safe_timestamp(value: str) -> str:
    return value.replace(":", "-")


def _incident_short_hash(incident_id: str) -> str:
    return hashlib.sha256(incident_id.encode("utf-8")).hexdigest()[:8]


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
