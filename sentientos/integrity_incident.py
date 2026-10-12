from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any

from sentientos.artifact_catalog import append_catalog_entry
from sentientos.private_file_custody import PrivateFileCustodyError, publish_immutable_bytes
from sentientos.integrity_pressure import (
    MAX_INCIDENT_ROW_BYTES,
    MAX_TRIGGERS_PER_INCIDENT,
    MAX_TRIGGER_CHARS,
)

INCIDENTS_DIR = Path("glow/forge/incidents")
INCIDENTS_FEED_PATH = Path("pulse/integrity_incidents.jsonl")
MAX_INCIDENT_ARTIFACT_BYTES = 1_048_576


class IntegrityIncidentFeedRecordError(ValueError):
    """An incident cannot be represented by the bounded pressure-feed schema."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class IntegrityIncidentArtifactError(ValueError):
    """An immutable incident artifact could not be safely represented or published."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


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
    incident_path = root / INCIDENTS_DIR / f"incident_{_safe_timestamp(incident.created_at)}_{_incident_identity_hash(incident.incident_id)}.json"
    # Validate the observation row before publishing the full incident artifact
    # so a record that the bounded reader cannot consume never poisons its feed.
    feed_row = _incident_feed_row(root, incident, incident_path, quarantine_activated=quarantine_activated)
    feed_bytes = _serialize_incident_feed_row(feed_row)
    artifact_bytes = _serialize_incident_artifact(incident)
    _publish_incident_artifact(root, incident_path, artifact_bytes)
    _append_incident_feed_bytes(root, feed_bytes)
    append_catalog_entry(
        root,
        kind="incident",
        artifact_id=incident.incident_id,
        relative_path=str(incident_path.relative_to(root)),
        schema_name="incident",
        schema_version=incident.schema_version,
        links={
            "incident_id": incident.incident_id,
            "trace_id": incident.governance_trace_id,
            "pack_id": incident.remediation_pack_id,
            "quarantine_activated": quarantine_activated,
        },
        summary={"severity": incident.severity, "enforcement_mode": incident.enforcement_mode},
        ts=incident.created_at,
    )
    return incident_path


def append_incident_feed(repo_root: Path, incident: Incident, incident_path: Path, *, quarantine_activated: bool = False) -> None:
    root = repo_root.resolve()
    row = _incident_feed_row(root, incident, incident_path, quarantine_activated=quarantine_activated)
    _append_incident_feed_bytes(root, _serialize_incident_feed_row(row))


def _incident_feed_row(
    root: Path, incident: Incident, incident_path: Path, *, quarantine_activated: bool,
) -> dict[str, object]:
    try:
        relative_path = str(incident_path.relative_to(root))
    except ValueError as exc:
        raise IntegrityIncidentFeedRecordError("incident_feed_path_outside_root") from exc
    return {
        "schema_version": 1,
        "incident_id": incident.incident_id,
        "created_at": incident.created_at,
        "severity": incident.severity,
        "enforcement_mode": incident.enforcement_mode,
        "quarantine_activated": quarantine_activated,
        "triggers": incident.triggers,
        "path": relative_path,
        "governance_trace_id": incident.governance_trace_id,
        "remediation_pack_id": incident.remediation_pack_id,
    }


def _serialize_incident_feed_row(row: dict[str, object]) -> bytes:
    timestamp = row.get("created_at")
    if not isinstance(timestamp, str) or not timestamp:
        raise IntegrityIncidentFeedRecordError("incident_feed_event_time_invalid")
    try:
        parsed_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IntegrityIncidentFeedRecordError("incident_feed_event_time_invalid") from exc
    if parsed_at.tzinfo is None:
        raise IntegrityIncidentFeedRecordError("incident_feed_event_time_invalid")
    if type(row.get("quarantine_activated")) is not bool:
        raise IntegrityIncidentFeedRecordError("incident_feed_quarantine_flag_invalid")
    if not isinstance(row.get("enforcement_mode"), str):
        raise IntegrityIncidentFeedRecordError("incident_feed_enforcement_mode_invalid")
    triggers = row.get("triggers")
    if not isinstance(triggers, list) or any(not isinstance(item, str) for item in triggers):
        raise IntegrityIncidentFeedRecordError("incident_feed_triggers_invalid")
    if len(triggers) > MAX_TRIGGERS_PER_INCIDENT or any(
        len(item) > MAX_TRIGGER_CHARS for item in triggers
    ):
        raise IntegrityIncidentFeedRecordError("incident_feed_trigger_limit_exceeded")
    try:
        encoded = (json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise IntegrityIncidentFeedRecordError("incident_feed_row_not_serializable") from exc
    if len(encoded) - 1 > MAX_INCIDENT_ROW_BYTES:
        raise IntegrityIncidentFeedRecordError("incident_feed_row_size_limit_exceeded")
    return encoded


def _serialize_incident_artifact(incident: Incident) -> bytes:
    try:
        encoded = (json.dumps(incident.to_dict(), indent=2, sort_keys=True,
            ensure_ascii=False) + "\n").encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise IntegrityIncidentArtifactError("incident_artifact_not_serializable") from exc
    if len(encoded) > MAX_INCIDENT_ARTIFACT_BYTES:
        raise IntegrityIncidentArtifactError("incident_artifact_size_limit_exceeded")
    return encoded


def _publish_incident_artifact(root: Path, path: Path, encoded: bytes) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise IntegrityIncidentArtifactError("incident_artifact_path_outside_root") from exc
    if len(encoded) > MAX_INCIDENT_ARTIFACT_BYTES:
        raise IntegrityIncidentArtifactError("incident_artifact_size_limit_exceeded")
    if os.name == "posix":
        try:
            publish_immutable_bytes(path, encoded,
                max_bytes=MAX_INCIDENT_ARTIFACT_BYTES,
                collision_code="incident_artifact_identity_conflict")
            return
        except PrivateFileCustodyError as exc:
            raise IntegrityIncidentArtifactError(
                "incident_artifact_publication_" + exc.code) from exc
    if os.name == "nt":
        # The Windows custody module currently provides reparse-safe reads but
        # no equivalent held-directory immutable publisher. Keep existing
        # Windows write behavior while refusing to overwrite an existing
        # artifact identity; the POSIX branch carries the stronger custody.
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError as exc:
            try:
                existing = path.read_bytes()
            except OSError as read_exc:
                raise IntegrityIncidentArtifactError(
                    "incident_artifact_existing_read_unavailable") from read_exc
            if existing != encoded:
                raise IntegrityIncidentArtifactError(
                    "incident_artifact_identity_conflict") from exc
        except OSError as exc:
            raise IntegrityIncidentArtifactError(
                "incident_artifact_publication_unavailable") from exc
        return
    raise IntegrityIncidentArtifactError("incident_artifact_publication_unsupported")


def _append_incident_feed_bytes(root: Path, encoded: bytes) -> None:
    target = root / INCIDENTS_FEED_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("ab") as handle:
        written = handle.write(encoded)
        if written != len(encoded):
            raise OSError("incident_feed_append_incomplete")
        handle.flush()


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


def _incident_identity_hash(incident_id: str) -> str:
    # Keep the full identity digest in the artifact name so distinct incident
    # identities cannot silently collide on a truncated filename suffix.
    return hashlib.sha256(incident_id.encode("utf-8")).hexdigest()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
