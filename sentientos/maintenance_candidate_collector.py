"""Fail-closed, proposal-only intake of canonical maintenance evidence.

The collector is deliberately an external file custodian.  It never invokes the
watchdog (or any other process) and its only mutations are no-clobber candidate
writes, its private lock, and its digest-chained receipt journal.
"""
from __future__ import annotations

from dataclasses import fields
import fcntl
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any, Mapping, Sequence

from sentientos import governed_improvement_signal_plane as signals
from sentientos import maintenance_activation_profiles as profiles
from sentientos import maintenance_candidate as candidates
from sentientos import maintenance_candidate_selector as selector
from sentientos import maintenance_loop_watchdog as watchdog
from sentientos import work_item_intake

CONFIG_SCHEMA = "sentientos.maintenance_candidate_collector_config:v1"
SCAN_SCHEMA = "sentientos.maintenance_candidate_collector_scan:v1"
RECEIPT_SCHEMA = "sentientos.maintenance_candidate_collection_receipt:v1"
RECEIPT_INSPECTION_SCHEMA = "sentientos.maintenance_candidate_collection_receipt_inspection:v1"
GOVERNED_SIGNAL_SCHEMA = "governed_improvement_signal_plane_evaluation:v1"
NORMALIZED_WORK_ITEM_SCHEMA = "sentientos.normalized_work_item_packet:v1"
SOURCE_SCHEMAS = frozenset({GOVERNED_SIGNAL_SCHEMA, NORMALIZED_WORK_ITEM_SCHEMA})
SOURCE_KINDS = frozenset({"governed_improvement_signal", "normalized_work_item"})
ZERO_DIGEST = "sha256:" + "0" * 64

_REQUIRED = {
    "schema_version", "repository_identity", "repository_root", "base_sha",
    "activation_profile_bundle_manifest_path", "watchdog_configuration_path",
    "collector_state_root", "maintenance_candidate_inbox",
    "governed_improvement_signal_source_roots", "normalized_work_item_source_roots",
    "allowed_source_schemas", "allowed_source_kinds", "maximum_source_records_per_scan",
    "maximum_candidates_per_collection", "maximum_input_bytes_per_record",
    "evaluation_time_required", "receipt_journal_path",
}
_ALLOWED = _REQUIRED | {"stop_marker", "config_digest"}


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def bytes_digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _closed(value: Mapping[str, Any], allowed: set[str], required: set[str]) -> None:
    if set(value) - allowed:
        raise ValueError("unknown_config_field")
    if not required.issubset(value):
        raise ValueError("missing_config_field")


def _existing_directory(value: object, *, label: str) -> Path:
    path = Path(str(value))
    if path.is_symlink() or not path.exists() or not stat.S_ISDIR(os.lstat(path).st_mode):
        raise ValueError(label + "_unsafe")
    return path.resolve(strict=True)


def _external(path: Path, repo: Path, *, label: str) -> None:
    if path == repo or repo in path.parents or path == repo / ".git" or (repo / ".git") in path.parents:
        raise ValueError(label + "_inside_repository")


def validate_config(value: Mapping[str, Any]) -> dict[str, Any]:
    _closed(value, _ALLOWED, _REQUIRED)
    if value["schema_version"] != CONFIG_SCHEMA:
        raise ValueError("invalid_config_schema")
    if value["evaluation_time_required"] is not True:
        raise ValueError("evaluation_time_must_be_required")
    for key in ("maximum_source_records_per_scan", "maximum_candidates_per_collection", "maximum_input_bytes_per_record"):
        if not isinstance(value[key], int) or isinstance(value[key], bool) or int(value[key]) < 1:
            raise ValueError("invalid_bound:" + key)
    kinds = tuple(sorted(str(x) for x in value["allowed_source_kinds"]))
    schemas = tuple(sorted(str(x) for x in value["allowed_source_schemas"]))
    if not kinds or not set(kinds).issubset(SOURCE_KINDS):
        raise ValueError("unsupported_source_kind")
    if not schemas or not set(schemas).issubset(SOURCE_SCHEMAS):
        raise ValueError("unsupported_source_schema")
    repo = _existing_directory(value["repository_root"], label="repository_root")
    if not (repo / ".git").exists():
        raise ValueError("repository_identity_unverifiable")
    result = dict(value)
    result["repository_root"] = str(repo)
    result["allowed_source_kinds"] = list(kinds)
    result["allowed_source_schemas"] = list(schemas)
    for key in ("governed_improvement_signal_source_roots", "normalized_work_item_source_roots"):
        roots = [_existing_directory(x, label="source_root") for x in value[key]]
        if not roots:
            raise ValueError("source_root_required")
        result[key] = sorted(str(x) for x in roots)
    state = _existing_directory(value["collector_state_root"], label="collector_state_root")
    inbox = _existing_directory(value["maintenance_candidate_inbox"], label="candidate_inbox")
    _external(state, repo, label="collector_state_root")
    _external(inbox, repo, label="candidate_inbox")
    if os.name == "posix" and stat.S_IMODE(os.lstat(state).st_mode) != 0o700:
        raise ValueError("collector_state_permissions_unsafe")
    result["collector_state_root"] = str(state)
    result["maintenance_candidate_inbox"] = str(inbox)
    receipt = Path(str(value["receipt_journal_path"])).absolute()
    if receipt.is_symlink() or receipt.parent.resolve(strict=True) != state:
        raise ValueError("receipt_custody_invalid")
    result["receipt_journal_path"] = str(receipt)
    for key in ("activation_profile_bundle_manifest_path", "watchdog_configuration_path"):
        path = Path(str(value[key])).resolve(strict=True)
        if path.is_symlink() or not path.is_file():
            raise ValueError(key + "_unsafe")
        result[key] = str(path)
    if value.get("stop_marker"):
        stop = Path(str(value["stop_marker"])).absolute()
        if stop.is_symlink() or stop.parent.resolve(strict=True) != state:
            raise ValueError("stop_marker_custody_invalid")
        result["stop_marker"] = str(stop)
    unsigned = {k: v for k, v in result.items() if k != "config_digest"}
    expected = digest(unsigned)
    if value.get("config_digest") not in (None, "", expected):
        raise ValueError("config_digest_mismatch")
    result["config_digest"] = expected
    return result


def load_config(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if p.is_symlink() or not p.is_file():
        raise ValueError("config_path_unsafe")
    payload = json.loads(p.read_bytes().decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("config_not_object")
    return validate_config(payload)


def _git_head(repo: Path) -> str:
    head = (repo / ".git" / "HEAD").read_text(encoding="ascii").strip()
    if head.startswith("ref: "):
        ref = repo / ".git" / head[5:]
        if ref.is_file():
            return ref.read_text(encoding="ascii").strip()
        for line in (repo / ".git" / "packed-refs").read_text(encoding="ascii").splitlines() if (repo / ".git" / "packed-refs").exists() else ():
            if line.endswith(" " + head[5:]):
                return line.split(" ", 1)[0]
        raise ValueError("repository_head_unresolved")
    return head


def _profile(cfg: Mapping[str, Any], evaluation_time: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    verified = profiles.verify_profile_bundle(cfg["activation_profile_bundle_manifest_path"], evaluation_time)
    if verified.get("status") != "profile_bundle_ready":
        raise ValueError("profile_bundle_not_ready")
    inspected = profiles.inspect_profile_bundle(cfg["activation_profile_bundle_manifest_path"], evaluation_time)
    manifest = inspected["manifest"]
    bundle = Path(str(manifest["output_directory"]))
    policy = selector.build_policy(json.loads((bundle / profiles.FILENAMES["selector_policy"]).read_text(encoding="utf-8")))
    return manifest, verified, policy.to_dict()


def _lock(cfg: Mapping[str, Any], *, nonblocking: bool) -> Any:
    path = Path(str(cfg["collector_state_root"])) / "collector.lock"
    handle = path.open("a+b")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | (fcntl.LOCK_NB if nonblocking else 0))
    except BlockingIOError:
        handle.close()
        raise ValueError("collector_lock_unavailable")
    return handle


def _doctor(cfg: Mapping[str, Any], evaluation_time: str) -> dict[str, Any]:
    reasons: list[str] = []
    try:
        if _git_head(Path(str(cfg["repository_root"]))) != cfg["base_sha"]:
            reasons.append("base_sha_mismatch")
        manifest, verified, profile_policy = _profile(cfg, evaluation_time)
        if manifest["repository_identity"] != cfg["repository_identity"] or Path(manifest["repository_root"]).resolve() != Path(cfg["repository_root"]):
            reasons.append("profile_repository_mismatch")
        if manifest["base_sha"] != cfg["base_sha"] or Path(manifest["inbox_root"]).resolve() != Path(cfg["maintenance_candidate_inbox"]):
            reasons.append("profile_collector_mismatch")
        wd = watchdog.load_config(cfg["watchdog_configuration_path"])
        if wd["base_sha"] != cfg["base_sha"] or Path(cfg["maintenance_candidate_inbox"]) not in [Path(x) for x in wd["candidate_inbox_roots"]]:
            reasons.append("watchdog_collector_mismatch")
        configured_policy = wd["selector_policy"]
        if not isinstance(configured_policy, Mapping):
            configured_policy = json.loads(Path(str(configured_policy)).read_text(encoding="utf-8"))
        if selector.build_policy(configured_policy).policy_digest != profile_policy["policy_digest"]:
            reasons.append("watchdog_profile_selector_mismatch")
        if Path(cfg.get("stop_marker", "")).is_file() if cfg.get("stop_marker") else False:
            reasons.append("stop_marker_present")
        lock = _lock(cfg, nonblocking=True); lock.close()
        _ = signals.validate_evaluation, candidates.adapt_governed_signal, candidates.adapt_work_item_packet, selector.select_candidate
        bundle_digest = verified["bundle_digest"]
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        reasons.append(str(exc))
        bundle_digest = None
    return {"schema_version": "sentientos.maintenance_candidate_collector_doctor:v1", "status": "collector_ready" if not reasons else "collector_blocked", "config_digest": cfg["config_digest"], "activation_profile_bundle_digest": bundle_digest, "reason_codes": sorted(set(reasons))}


def doctor(config: Mapping[str, Any], *, evaluation_time: str) -> dict[str, Any]:
    try:
        cfg = validate_config(config)
        return _doctor(cfg, evaluation_time)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return {"schema_version": "sentientos.maintenance_candidate_collector_doctor:v1", "status": "collector_blocked", "reason_codes": [str(exc)]}


def _work_packet(payload: Mapping[str, Any]) -> work_item_intake.NormalizedWorkItemPacket:
    raw = dict(payload)
    schema = raw.pop("schema_version", None)
    if schema != NORMALIZED_WORK_ITEM_SCHEMA:
        raise ValueError("unknown_source_schema")
    allowed = {f.name for f in fields(work_item_intake.NormalizedWorkItemPacket)}
    if set(raw) != allowed:
        raise ValueError("normalized_work_item_closed_schema_invalid")
    packet = work_item_intake.NormalizedWorkItemPacket(**raw)
    if work_item_intake.summarize_work_item_packet(packet) != raw:
        raise ValueError("normalized_work_item_not_canonical")
    seed = json.dumps({"source_kind": packet.source_kind, "source_ref": packet.source_ref,
                       "title": packet.title, "requested_outcome": packet.requested_outcome},
                      sort_keys=True, separators=(",", ":"))
    expected_id = "wi_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    if (packet.work_item_id != expected_id or packet.source_kind not in work_item_intake.WORK_ITEM_SOURCE_KINDS
            or packet.intake_status not in work_item_intake.INTAKE_STATUSES
            or packet.risk_class not in work_item_intake.RISK_CLASSES
            or packet.agent_execution_is_permitted_by_this_packet is not False):
        raise ValueError("normalized_work_item_semantic_validation_failed")
    return packet


def _source_files(cfg: Mapping[str, Any]) -> list[tuple[str, Path]]:
    groups = (("governed_improvement_signal", cfg["governed_improvement_signal_source_roots"]), ("normalized_work_item", cfg["normalized_work_item_source_roots"]))
    found: list[tuple[str, Path]] = []
    for kind, roots in groups:
        if kind not in cfg["allowed_source_kinds"]:
            continue
        for root_value in roots:
            root = Path(root_value)
            for path in sorted(root.glob("*.json"), key=lambda p: p.name):
                found.append((kind, path))
    return found[: int(cfg["maximum_source_records_per_scan"])]


def scan(config: Mapping[str, Any], *, evaluation_time: str) -> dict[str, Any]:
    cfg = validate_config(config)
    _, verified, policy = _profile(cfg, evaluation_time)
    records: list[dict[str, Any]] = []
    adapted: list[candidates.MaintenanceCandidate] = []
    bindings: dict[str, list[dict[str, Any]]] = {}
    for kind, path in _source_files(cfg):
        row: dict[str, Any] = {"source_kind": kind, "source_path": str(path)}
        try:
            if path.is_symlink() or not path.is_file():
                raise ValueError("source_path_unsafe")
            raw = path.read_bytes()
            row["source_byte_digest"] = bytes_digest(raw)
            if len(raw) > int(cfg["maximum_input_bytes_per_record"]):
                raise ValueError("source_oversized")
            payload = json.loads(raw.decode("utf-8"))
            if not isinstance(payload, Mapping):
                raise ValueError("source_not_object")
            if kind == "governed_improvement_signal":
                schema = payload.get("schema")
                if schema not in cfg["allowed_source_schemas"]:
                    raise ValueError("unknown_source_schema")
                valid, why = signals.validate_evaluation(payload)
                if not valid:
                    raise ValueError("governed_signal_invalid:" + ",".join(why))
                source_values = payload["batch"]["signals"]
                built = [candidates.adapt_governed_signal(signals.ImprovementSignal(**x), base_repository_sha=cfg["base_sha"]) for x in source_values]
            else:
                if NORMALIZED_WORK_ITEM_SCHEMA not in cfg["allowed_source_schemas"]:
                    raise ValueError("unknown_source_schema")
                packet = _work_packet(payload)
                schema = NORMALIZED_WORK_ITEM_SCHEMA
                built = [candidates.adapt_work_item_packet(packet, base_repository_sha=cfg["base_sha"])]
            row.update(source_schema=schema, source_status="source_ready", semantic_identities=sorted(c.source_semantic_digest for c in built))
            for candidate in built:
                adapted.append(candidate)
                bindings.setdefault(candidate.candidate_id, []).append({"source_path": str(path), "source_byte_digest": row["source_byte_digest"], "source_semantic_identity": candidate.source_semantic_digest})
        except (OSError, ValueError, KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            row.update(source_status="source_blocked", reason_codes=[str(exc)])
        records.append(row)
    candidate_set = candidates.normalize_candidate_set(adapted)
    # Normalization is the identity authority.  Its canonical representative can
    # intentionally have a different ID from an input adapter object, so bind the
    # representative back to source records by the same semantic grouping fields
    # rather than assuming input IDs survive normalization.
    for item in candidate_set["canonical_candidates"]:
        matches: list[dict[str, Any]] = []
        for original in adapted:
            if (original.objective == item["objective"] and original.candidate_kind == item["candidate_kind"]
                    and tuple(original.declared_subject_paths) == tuple(item["declared_subject_paths"])):
                matches.extend(bindings.get(original.candidate_id, ()))
        bindings[item["candidate_id"]] = sorted(matches, key=lambda x: (x["source_path"], x["source_byte_digest"]))
    decisions: dict[str, Any] = {}
    for item in candidate_set["canonical_candidates"]:
        one = candidates.normalize_candidate_set([selector.candidate_from_dict(item)])
        decisions[item["candidate_id"]] = selector.select_candidate(one, policy, journal_state_root=Path(watchdog.load_config(cfg["watchdog_configuration_path"])["state_root"]))
    return {"schema_version": SCAN_SCHEMA, "status": "scan_ready" if all(x["source_status"] == "source_ready" for x in records) else "scan_blocked", "config_digest": cfg["config_digest"], "activation_profile_bundle_digest": verified["bundle_digest"], "selector_policy_digest": policy["policy_digest"], "sources": records, "source_count": len(records), "candidate_set": candidate_set, "candidate_bindings": bindings, "eligibility_decisions": decisions, "inbox_write_status": {}, "receipt_identities": []}


def _receipt_records(path: Path, *, allow_partial_final_line: bool = False) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if path.is_symlink() or not path.is_file():
        raise ValueError("receipt_journal_unsafe")
    data = path.read_bytes()
    lines = data.splitlines(keepends=True)
    result: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        if not line.endswith(b"\n"):
            if allow_partial_final_line and index == len(lines) - 1:
                break
            raise ValueError("receipt_truncated")
        result.append(json.loads(line.decode("utf-8")))
    return result


def inspect_receipts(config: Mapping[str, Any], *, allow_partial_final_line: bool = False) -> dict[str, Any]:
    cfg = validate_config(config); path = Path(cfg["receipt_journal_path"])
    reasons: list[str] = []
    try:
        rows = _receipt_records(path, allow_partial_final_line=allow_partial_final_line)
        predecessor = ZERO_DIGEST
        for sequence, row in enumerate(rows, 1):
            claimed = row.get("receipt_digest")
            if row.get("schema_version") != RECEIPT_SCHEMA or row.get("sequence") != sequence or row.get("predecessor_receipt_digest") != predecessor or claimed != digest({k: v for k, v in row.items() if k != "receipt_digest"}):
                raise ValueError("receipt_chain_invalid")
            target = Path(cfg["maintenance_candidate_inbox"]) / str(row["destination_filename"])
            if not target.is_file() or bytes_digest(target.read_bytes()) != row["canonical_candidate_byte_digest"]:
                raise ValueError("receipt_candidate_binding_invalid")
            predecessor = str(claimed)
    except (OSError, ValueError, KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        reasons.append(str(exc)); rows = []
    return {"schema_version": RECEIPT_INSPECTION_SCHEMA, "status": "receipts_ready" if not reasons else "receipts_blocked", "receipt_count": len(rows), "head_receipt_digest": rows[-1]["receipt_digest"] if rows else ZERO_DIGEST, "reason_codes": reasons, "receipts": rows}


def _append_receipt(path: Path, row: dict[str, Any]) -> None:
    data = canonical_json_bytes(row) + b"\n"
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "ab") as handle:
        handle.write(data); handle.flush(); os.fsync(handle.fileno())


def collect_once(config: Mapping[str, Any], *, evaluation_time: str) -> dict[str, Any]:
    cfg = validate_config(config); readiness = _doctor(cfg, evaluation_time)
    if readiness["status"] != "collector_ready":
        return {"schema_version": "sentientos.maintenance_candidate_collection:v1", "status": "collection_blocked", "reason_codes": readiness["reason_codes"]}
    lock = _lock(cfg, nonblocking=True)
    try:
        scanned = scan(cfg, evaluation_time=evaluation_time)
        if scanned["status"] != "scan_ready":
            return {"schema_version": "sentientos.maintenance_candidate_collection:v1", "status": "collection_blocked", "scan": scanned, "reason_codes": ["source_scan_blocked"]}
        receipt_path = Path(cfg["receipt_journal_path"]); inspection = inspect_receipts(cfg)
        if inspection["status"] != "receipts_ready":
            return {"schema_version": "sentientos.maintenance_candidate_collection:v1", "status": "collection_blocked", "reason_codes": inspection["reason_codes"]}
        receipts = inspection["receipts"]; existing_keys = {(x["canonical_candidate_id"], x["canonical_candidate_revision_digest"]) for x in receipts}
        writes: dict[str, str] = {}; appended: list[str] = []
        eligible = [x for x in scanned["candidate_set"]["canonical_candidates"] if scanned["eligibility_decisions"][x["candidate_id"]]["result_status"] == "ready_for_scope_admission"]
        for item in eligible[: int(cfg["maximum_candidates_per_collection"])]:
            candidate = selector.candidate_from_dict(item); raw = candidate.canonical_bytes() + b"\n"
            revision = candidate.candidate_revision_digest.split(":", 1)[-1]
            filename = f"{candidate.candidate_id}.{revision}.json"; target = Path(cfg["maintenance_candidate_inbox"]) / filename
            if target.exists():
                if target.is_symlink() or target.read_bytes() != raw:
                    return {"schema_version": "sentientos.maintenance_candidate_collection:v1", "status": "collection_blocked", "reason_codes": ["candidate_destination_conflict"], "scan": scanned}
                writes[candidate.candidate_id] = "reused"
            else:
                fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
                with os.fdopen(fd, "wb") as handle:
                    handle.write(raw); handle.flush(); os.fsync(handle.fileno())
                writes[candidate.candidate_id] = "created"
            key = (candidate.candidate_id, candidate.candidate_revision_digest)
            if key not in existing_keys:
                source_rows = scanned["candidate_bindings"].get(candidate.candidate_id, [])
                body = {"schema_version": RECEIPT_SCHEMA, "sequence": len(receipts) + 1, "predecessor_receipt_digest": receipts[-1]["receipt_digest"] if receipts else ZERO_DIGEST, "source_artifacts": source_rows, "canonical_candidate_id": candidate.candidate_id, "canonical_candidate_revision_digest": candidate.candidate_revision_digest, "canonical_candidate_byte_digest": bytes_digest(raw), "activation_profile_bundle_digest": scanned["activation_profile_bundle_digest"], "selector_policy_digest": scanned["selector_policy_digest"], "repository_identity": cfg["repository_identity"], "base_sha": cfg["base_sha"], "destination_inbox_identity": digest(str(Path(cfg["maintenance_candidate_inbox"]))), "destination_filename": filename, "write_status": writes[candidate.candidate_id]}
                body["receipt_digest"] = digest(body); _append_receipt(receipt_path, body); receipts.append(body); existing_keys.add(key); appended.append(body["receipt_digest"])
        scanned["inbox_write_status"] = writes; scanned["receipt_identities"] = appended
        return {"schema_version": "sentientos.maintenance_candidate_collection:v1", "status": "collection_ready", "candidates_written": sum(v == "created" for v in writes.values()), "candidates_reused": sum(v == "reused" for v in writes.values()), "receipts_appended": len(appended), "scan": scanned}
    finally:
        lock.close()


def inspect(config: Mapping[str, Any], *, evaluation_time: str) -> dict[str, Any]:
    cfg = validate_config(config); scanned = scan(cfg, evaluation_time=evaluation_time); receipts = inspect_receipts(cfg)
    return {"schema_version": "sentientos.maintenance_candidate_collector_inspection:v1", "status": "inspection_ready" if scanned["status"] == "scan_ready" and receipts["status"] == "receipts_ready" else "inspection_blocked", "config_digest": cfg["config_digest"], "scan": scanned, "receipts": receipts}


def print_run_command(config_path: str | Path, *, evaluation_time: str, python_executable: str = "python") -> dict[str, Any]:
    return {"schema_version": "sentientos.maintenance_candidate_collector_run_command:v1", "status": "run_command_ready", "argv": [python_executable, str(Path(__file__).parents[1] / "scripts" / "maintenance_candidate_collector.py"), "--config", str(Path(config_path)), "--evaluation-time", evaluation_time, "collect-once"], "scheduler_installation": False, "watchdog_invocation": False}


__all__ = ["CONFIG_SCHEMA", "SCAN_SCHEMA", "RECEIPT_SCHEMA", "GOVERNED_SIGNAL_SCHEMA", "NORMALIZED_WORK_ITEM_SCHEMA", "SOURCE_SCHEMAS", "SOURCE_KINDS", "validate_config", "load_config", "doctor", "scan", "collect_once", "inspect", "inspect_receipts", "print_run_command", "canonical_json_bytes", "digest"]
