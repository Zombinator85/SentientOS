"""Metadata-only local effect transaction ledger.

This wing connects the bounded Tier-1 local diagnostic effect records and the
exact-artifact rollback records into an integrity ledger. Building entries,
ledgers, and lifecycle reports performs no new host effect. The only permitted
mutation in this module is the optional explicit write of one caller-supplied
ledger artifact path.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, NamedTuple, Sequence

DEFAULT_CREATED_AT = "1970-01-01T00:00:00+00:00"

TRANSACTION_STATUSES = frozenset({
    "local_effect_transaction_open",
    "local_effect_transaction_effect_recorded",
    "local_effect_transaction_postcondition_passed",
    "local_effect_transaction_audit_recorded",
    "local_effect_transaction_rollback_available",
    "local_effect_transaction_rollback_performed",
    "local_effect_transaction_rollback_postcondition_passed",
    "local_effect_transaction_rollback_audit_recorded",
    "local_effect_transaction_closed",
    "local_effect_transaction_orphaned",
    "local_effect_transaction_incomplete",
    "local_effect_transaction_contradicted",
    "local_effect_transaction_invalid",
})
LEDGER_STATUSES = frozenset({
    "local_effect_transaction_ledger_current",
    "local_effect_transaction_ledger_current_with_warnings",
    "local_effect_transaction_ledger_incomplete",
    "local_effect_transaction_ledger_contradicted",
    "local_effect_transaction_ledger_invalid",
})
LIFECYCLE_STATUSES = frozenset({
    "local_effect_lifecycle_complete",
    "local_effect_lifecycle_complete_with_rollback",
    "local_effect_lifecycle_open",
    "local_effect_lifecycle_orphaned_effect",
    "local_effect_lifecycle_missing_postcondition",
    "local_effect_lifecycle_missing_audit",
    "local_effect_lifecycle_missing_rollback_plan",
    "local_effect_lifecycle_rollback_pending",
    "local_effect_lifecycle_rollback_incomplete",
    "local_effect_lifecycle_contradicted",
    "local_effect_lifecycle_invalid",
})
ARTIFACT_STATUSES = frozenset({
    "local_effect_transaction_ledger_artifact_written",
    "local_effect_transaction_ledger_artifact_blocked",
    "local_effect_transaction_ledger_artifact_incomplete",
    "local_effect_transaction_ledger_artifact_contradicted",
})
EVENT_KINDS = frozenset({
    "diagnostic_effect_requested",
    "diagnostic_effect_performed",
    "diagnostic_effect_receipt_recorded",
    "diagnostic_postcondition_passed",
    "diagnostic_production_audit_recorded",
    "diagnostic_rollback_plan_recorded",
    "diagnostic_exact_rollback_requested",
    "diagnostic_exact_rollback_performed",
    "diagnostic_exact_rollback_receipt_recorded",
    "diagnostic_rollback_postcondition_passed",
    "diagnostic_rollback_audit_recorded",
    "transaction_closed",
    "transaction_blocked",
    "transaction_contradicted",
})
BLOCKED_ACTION_LABELS = (
    "general_cleanup",
    "directory_cleanup",
    "recursive_delete",
    "wildcard_delete",
    "unrelated_file_delete",
    "fan_pwm_write",
    "thermal_actuation",
    "power_profile_mutation",
    "process_kill",
    "service_restart",
    "package_install",
    "driver_install",
    "provider_invocation",
    "network_egress",
    "prompt_assembly",
    "federation_transport",
    "remote_execution",
    "subprocess_execution",
    "shell_execution",
    "os_backend_invocation",
    "control_plane_admission_execution",
    "hardware_control",
)
_FORBIDDEN_TRUE_FIELDS = (
    "general_cleanup_performed",
    "general_cleanup_requested",
    "directory_cleanup_performed",
    "directory_cleanup_requested",
    "recursive_delete_performed",
    "recursive_delete_requested",
    "wildcard_delete_performed",
    "wildcard_delete_requested",
    "unrelated_file_delete_performed",
    "unrelated_file_delete_requested",
    "fan_pwm_write_performed",
    "thermal_actuation_performed",
    "power_profile_mutation_performed",
    "process_kill_performed",
    "service_restart_performed",
    "package_install_performed",
    "driver_install_performed",
    "provider_invocation_performed",
    "network_performed",
    "prompt_assembly_performed",
    "subprocess_performed",
    "shell_performed",
    "os_backend_invoked",
    "os_backend_invocation_performed",
    "control_plane_admission_execution_performed",
    "hardware_control_performed",
)
_ALLOWED_ROLLBACK_TRUE_FIELDS = frozenset({"real_rollback_performed", "file_delete_performed", "host_mutation_performed"})


@dataclass(frozen=True)
class LocalEffectTransactionLedgerValidationResult:
    ok: bool
    findings: tuple[str, ...] = ()


@dataclass(frozen=True)
class LocalEffectTransactionEntry:
    entry_id: str
    transaction_id: str
    event_kind: str
    source_record_id: str
    source_record_digest: str
    previous_entry_digest: str | None
    transaction_status: str
    output_path: str | None
    artifact_digest: str | None
    evidence_summary: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    ledger_entry_only: bool = True
    performs_no_new_effect: bool = True
    host_mutation_performed: bool = False
    file_delete_performed: bool = False
    network_performed: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False
    subprocess_performed: bool = False
    shell_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LocalEffectTransactionLedger:
    ledger_id: str
    transaction_id: str
    entries: tuple[LocalEffectTransactionEntry, ...]
    ledger_status: str
    current_transaction_status: str
    effect_receipt_id: str | None
    postcondition_check_id: str | None
    production_audit_id: str | None
    rollback_plan_id: str | None
    rollback_receipt_id: str | None
    rollback_postcondition_check_id: str | None
    rollback_audit_id: str | None
    open_issue_codes: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    transaction_ledger_only: bool = True
    performs_no_new_effect: bool = True
    host_mutation_performed: bool = False
    network_performed: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["entries"] = [entry.to_dict() for entry in self.entries]
        return payload


@dataclass(frozen=True)
class LocalEffectTransactionLifecycleReport:
    report_id: str
    ledger_id: str
    transaction_id: str
    lifecycle_status: str
    present_event_kinds: tuple[str, ...]
    missing_event_kinds: tuple[str, ...]
    orphan_codes: tuple[str, ...]
    contradiction_codes: tuple[str, ...]
    closure_codes: tuple[str, ...]
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    lifecycle_report_only: bool = True
    performs_no_new_effect: bool = True
    host_mutation_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LocalEffectTransactionLedgerArtifactReceipt:
    receipt_id: str
    ledger_id: str
    output_path: str
    artifact_digest: str
    byte_count: int
    artifact_status: str
    warning_codes: tuple[str, ...]
    risk_codes: tuple[str, ...]
    created_at: str
    digest: str
    metadata_only: bool = True
    ledger_artifact_receipt_only: bool = True
    local_file_write_performed: bool = False
    host_mutation_performed: bool = False
    network_performed: bool = False
    provider_invocation_performed: bool = False
    prompt_assembly_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LocalEffectTransactionLedgerBundle(NamedTuple):
    ledger: LocalEffectTransactionLedger
    lifecycle_report: LocalEffectTransactionLifecycleReport


def _source_payload(source: Any | None) -> dict[str, Any]:
    if source is None:
        return {}
    if hasattr(source, "to_dict"):
        return dict(source.to_dict())
    return dict(source)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _without_digest(payload: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    data["digest"] = ""
    return data


def local_effect_transaction_digest(record_or_payload: Any) -> str:
    payload = _source_payload(record_or_payload)
    payload["digest"] = ""
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


local_effect_transaction_entry_digest = local_effect_transaction_digest
local_effect_transaction_ledger_digest = local_effect_transaction_digest
local_effect_transaction_lifecycle_report_digest = local_effect_transaction_digest
local_effect_transaction_ledger_artifact_receipt_digest = local_effect_transaction_digest


def _digest_id(prefix: str, payload: Mapping[str, Any]) -> str:
    return prefix + hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:16]


def _tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)


def _record_digest(record: Any) -> str:
    payload = _source_payload(record)
    supplied = payload.get("digest")
    if isinstance(supplied, str) and supplied.startswith("sha256:") and len(supplied) == 71:
        return supplied
    return "sha256:" + hashlib.sha256(_canonical_json(_without_digest(payload)).encode("utf-8")).hexdigest()


def _record_id(record: Any, candidates: Sequence[str]) -> str:
    payload = _source_payload(record)
    for name in candidates:
        if payload.get(name):
            return str(payload[name])
    return _digest_id("source-record-", payload)


def _transaction_id_from_records(records: Sequence[Any]) -> str:
    for record in records:
        payload = _source_payload(record)
        for name in ("source_effect_receipt_id", "effect_receipt_id", "receipt_id"):
            value = payload.get(name)
            if value:
                return "local-effect-transaction-" + str(value).replace("local-diagnostic-effect-receipt-", "")
    material = tuple(_record_digest(record) for record in records)
    return _digest_id("local-effect-transaction-", {"records": material})


def _blocked_actions_from_record(record: Any) -> tuple[str, ...]:
    payload = _source_payload(record)
    labels = set(_tuple(payload.get("blocked_actions")))
    for field in _FORBIDDEN_TRUE_FIELDS:
        if payload.get(field):
            labels.add(field.replace("_performed", "").replace("_requested", ""))
    return tuple(sorted(labels))


def _contradiction_codes_for_record(event_kind: str, record: Any) -> tuple[str, ...]:
    payload = _source_payload(record)
    codes: list[str] = []
    supplied = payload.get("digest")
    if supplied and not (isinstance(supplied, str) and supplied.startswith("sha256:") and len(supplied) == 71):
        codes.append(f"digest_mismatch:{event_kind}")
    for field in _FORBIDDEN_TRUE_FIELDS:
        if payload.get(field):
            codes.append(f"forbidden_claim:{event_kind}:{field}")
    return tuple(codes)


def build_local_effect_transaction_entry(
    *,
    transaction_id: str,
    event_kind: str,
    source_record: Any,
    transaction_status: str,
    previous_entry_digest: str | None = None,
    evidence_summary: Sequence[str] = (),
    created_at: str | None = None,
) -> LocalEffectTransactionEntry:
    if event_kind not in EVENT_KINDS:
        raise ValueError(f"unknown event kind: {event_kind}")
    if transaction_status not in TRANSACTION_STATUSES:
        raise ValueError(f"unknown transaction status: {transaction_status}")
    payload = _source_payload(source_record)
    id_candidates = ("receipt_id", "check_id", "audit_id", "plan_id", "result_id", "request_id")
    if "postcondition" in event_kind:
        id_candidates = ("check_id", "receipt_id", "audit_id", "plan_id", "result_id", "request_id")
    elif "audit" in event_kind:
        id_candidates = ("audit_id", "receipt_id", "check_id", "plan_id", "result_id", "request_id")
    elif "plan" in event_kind:
        id_candidates = ("plan_id", "receipt_id", "check_id", "audit_id", "result_id", "request_id")
    elif event_kind.endswith("requested"):
        id_candidates = ("request_id", "receipt_id", "check_id", "audit_id", "plan_id", "result_id")
    elif event_kind.endswith("performed"):
        id_candidates = ("result_id", "receipt_id", "check_id", "audit_id", "plan_id", "request_id")
    entry_payload: dict[str, Any] = {
        "entry_id": "",
        "transaction_id": transaction_id,
        "event_kind": event_kind,
        "source_record_id": _record_id(source_record, id_candidates),
        "source_record_digest": _record_digest(source_record),
        "previous_entry_digest": previous_entry_digest,
        "transaction_status": transaction_status,
        "output_path": payload.get("output_path") or payload.get("expected_output_path"),
        "artifact_digest": payload.get("artifact_digest") or payload.get("expected_artifact_digest") or payload.get("observed_artifact_digest"),
        "evidence_summary": _tuple(evidence_summary or payload.get("evidence_summary") or (event_kind,)),
        "blocked_actions": _blocked_actions_from_record(source_record) or BLOCKED_ACTION_LABELS,
        "warning_codes": _tuple(payload.get("warning_codes")),
        "risk_codes": _tuple(payload.get("risk_codes")),
        "created_at": created_at or str(payload.get("created_at") or DEFAULT_CREATED_AT),
        "digest": "",
        "metadata_only": True,
        "ledger_entry_only": True,
        "performs_no_new_effect": True,
        "host_mutation_performed": False,
        "file_delete_performed": False,
        "network_performed": False,
        "provider_invocation_performed": False,
        "prompt_assembly_performed": False,
        "subprocess_performed": False,
        "shell_performed": False,
    }
    entry_payload["entry_id"] = _digest_id("local-effect-transaction-entry-", entry_payload)
    entry_payload["digest"] = local_effect_transaction_entry_digest(entry_payload)
    return LocalEffectTransactionEntry(**entry_payload)


def _entry_specs(**records: Any) -> tuple[tuple[str, Any, str, tuple[str, ...]], ...]:
    specs = []
    mapping = (
        ("effect_request", "diagnostic_effect_requested", "local_effect_transaction_open", ("diagnostic effect request recorded",)),
        ("effect_result", "diagnostic_effect_performed", "local_effect_transaction_effect_recorded", ("diagnostic effect result recorded",)),
        ("effect_receipt", "diagnostic_effect_receipt_recorded", "local_effect_transaction_effect_recorded", ("real effect receipt recorded",)),
        ("postcondition_check", "diagnostic_postcondition_passed", "local_effect_transaction_postcondition_passed", ("diagnostic postcondition passed",)),
        ("production_audit", "diagnostic_production_audit_recorded", "local_effect_transaction_audit_recorded", ("production audit receipt recorded",)),
        ("rollback_plan", "diagnostic_rollback_plan_recorded", "local_effect_transaction_rollback_available", ("exact artifact rollback plan recorded",)),
        ("exact_rollback_request", "diagnostic_exact_rollback_requested", "local_effect_transaction_rollback_available", ("exact rollback request recorded",)),
        ("exact_rollback_result", "diagnostic_exact_rollback_performed", "local_effect_transaction_rollback_performed", ("exact rollback result recorded",)),
        ("exact_rollback_receipt", "diagnostic_exact_rollback_receipt_recorded", "local_effect_transaction_rollback_performed", ("exact rollback receipt recorded",)),
        ("rollback_postcondition_check", "diagnostic_rollback_postcondition_passed", "local_effect_transaction_rollback_postcondition_passed", ("rollback postcondition passed",)),
        ("rollback_audit", "diagnostic_rollback_audit_recorded", "local_effect_transaction_rollback_audit_recorded", ("rollback audit receipt recorded",)),
    )
    for key, event_kind, status, evidence in mapping:
        if records.get(key) is not None:
            specs.append((event_kind, records[key], status, evidence))
    return tuple(specs)


def _classify(events: Sequence[str], contradiction_codes: Sequence[str]) -> tuple[str, str, tuple[str, ...]]:
    event_set = set(events)
    issues: list[str] = []
    if contradiction_codes or "transaction_contradicted" in event_set:
        codes = tuple(contradiction_codes) or ("transaction_contradicted",)
        return "local_effect_transaction_ledger_contradicted", "local_effect_transaction_contradicted", codes
    if "diagnostic_effect_receipt_recorded" not in event_set:
        return "local_effect_transaction_ledger_invalid", "local_effect_transaction_invalid", ("missing_effect_receipt",)
    if "diagnostic_postcondition_passed" not in event_set:
        issues.append("missing_postcondition")
    if "diagnostic_production_audit_recorded" not in event_set:
        issues.append("missing_production_audit")
    if "diagnostic_rollback_plan_recorded" not in event_set:
        issues.append("missing_rollback_plan")
    has_rollback = "diagnostic_exact_rollback_receipt_recorded" in event_set
    if not has_rollback:
        issues.append("rollback_pending")
    else:
        if "diagnostic_rollback_postcondition_passed" not in event_set:
            issues.append("missing_rollback_postcondition")
        if "diagnostic_rollback_audit_recorded" not in event_set:
            issues.append("missing_rollback_audit")
    if issues:
        status = "local_effect_transaction_orphaned" if issues[0] in {"missing_postcondition", "missing_production_audit"} else "local_effect_transaction_incomplete"
        return "local_effect_transaction_ledger_incomplete", status, tuple(issues)
    return "local_effect_transaction_ledger_current", "local_effect_transaction_closed", ()


def build_local_effect_transaction_ledger(
    entries: Sequence[LocalEffectTransactionEntry],
    *,
    transaction_id: str | None = None,
    created_at: str = DEFAULT_CREATED_AT,
    allow_duplicate_event_kinds: bool = False,
) -> LocalEffectTransactionLedger:
    entry_tuple = tuple(entries)
    tx = transaction_id or (entry_tuple[0].transaction_id if entry_tuple else _digest_id("local-effect-transaction-", {"empty": True}))
    events = [entry.event_kind for entry in entry_tuple]
    contradiction_codes: list[str] = []
    if len(set(events)) != len(events) and not allow_duplicate_event_kinds:
        duplicates = sorted({event for event in events if events.count(event) > 1})
        contradiction_codes.extend(f"duplicate_event_kind:{event}" for event in duplicates)
    for index, entry in enumerate(entry_tuple):
        validation = validate_local_effect_transaction_entry(entry)
        contradiction_codes.extend(validation.findings)
        if entry.event_kind == "transaction_contradicted":
            contradiction_codes.extend(entry.evidence_summary or ("transaction_contradicted",))
        expected_previous = entry_tuple[index - 1].digest if index else None
        if entry.previous_entry_digest != expected_previous:
            contradiction_codes.append(f"entry_digest_chain_mismatch:{entry.event_kind}")
    ledger_status, current_status, issues = _classify(events, contradiction_codes)
    ids = {entry.event_kind: entry.source_record_id for entry in entry_tuple}
    payload: dict[str, Any] = {
        "ledger_id": "",
        "transaction_id": tx,
        "entries": entry_tuple,
        "ledger_status": ledger_status,
        "current_transaction_status": current_status,
        "effect_receipt_id": ids.get("diagnostic_effect_receipt_recorded"),
        "postcondition_check_id": ids.get("diagnostic_postcondition_passed"),
        "production_audit_id": ids.get("diagnostic_production_audit_recorded"),
        "rollback_plan_id": ids.get("diagnostic_rollback_plan_recorded"),
        "rollback_receipt_id": ids.get("diagnostic_exact_rollback_receipt_recorded"),
        "rollback_postcondition_check_id": ids.get("diagnostic_rollback_postcondition_passed"),
        "rollback_audit_id": ids.get("diagnostic_rollback_audit_recorded"),
        "open_issue_codes": tuple(issues),
        "blocked_actions": tuple(sorted(set().union(*(set(entry.blocked_actions) for entry in entry_tuple)))) if entry_tuple else BLOCKED_ACTION_LABELS,
        "warning_codes": tuple(sorted(set().union(*(set(entry.warning_codes) for entry in entry_tuple), set(issues)))) if entry_tuple else tuple(issues),
        "risk_codes": tuple(sorted(set().union(*(set(entry.risk_codes) for entry in entry_tuple), {"metadata_only_transaction_integrity_ledger"}))),
        "created_at": created_at,
        "digest": "",
        "metadata_only": True,
        "transaction_ledger_only": True,
        "performs_no_new_effect": True,
        "host_mutation_performed": False,
        "network_performed": False,
        "provider_invocation_performed": False,
        "prompt_assembly_performed": False,
    }
    payload["ledger_id"] = _digest_id("local-effect-transaction-ledger-", {**payload, "entries": [entry.to_dict() for entry in entry_tuple]})
    digest_payload = {**payload, "entries": [entry.to_dict() for entry in entry_tuple]}
    payload["digest"] = local_effect_transaction_ledger_digest(digest_payload)
    return LocalEffectTransactionLedger(**payload)


def build_local_effect_transaction_lifecycle_report(ledger: LocalEffectTransactionLedger, *, created_at: str | None = None) -> LocalEffectTransactionLifecycleReport:
    present = tuple(entry.event_kind for entry in ledger.entries)
    present_set = set(present)
    missing: list[str] = []
    required = ("diagnostic_effect_receipt_recorded", "diagnostic_postcondition_passed", "diagnostic_production_audit_recorded", "diagnostic_rollback_plan_recorded")
    for event in required:
        if event not in present_set:
            missing.append(event)
    if "diagnostic_exact_rollback_receipt_recorded" in present_set:
        for event in ("diagnostic_rollback_postcondition_passed", "diagnostic_rollback_audit_recorded"):
            if event not in present_set:
                missing.append(event)
    contradiction_codes = tuple(code for code in ledger.open_issue_codes if "contradict" in code or "forbidden" in code or "duplicate_event_kind" in code or "digest_mismatch" in code or "chain_mismatch" in code)
    orphan_codes: tuple[str, ...] = ()
    closure_codes: tuple[str, ...] = ()
    if ledger.ledger_status == "local_effect_transaction_ledger_invalid":
        status = "local_effect_lifecycle_invalid"
    elif ledger.ledger_status == "local_effect_transaction_ledger_contradicted" or contradiction_codes:
        status = "local_effect_lifecycle_contradicted"
    elif "diagnostic_postcondition_passed" not in present_set:
        status = "local_effect_lifecycle_missing_postcondition"
        orphan_codes = ("effect_receipt_without_postcondition",)
    elif "diagnostic_production_audit_recorded" not in present_set:
        status = "local_effect_lifecycle_missing_audit"
        orphan_codes = ("effect_receipt_without_audit",)
    elif "diagnostic_rollback_plan_recorded" not in present_set:
        status = "local_effect_lifecycle_missing_rollback_plan"
    elif "diagnostic_exact_rollback_receipt_recorded" not in present_set:
        status = "local_effect_lifecycle_rollback_pending"
    elif "diagnostic_rollback_postcondition_passed" not in present_set or "diagnostic_rollback_audit_recorded" not in present_set:
        status = "local_effect_lifecycle_rollback_incomplete"
    else:
        status = "local_effect_lifecycle_complete_with_rollback"
        closure_codes = ("effect_postcondition_audit_rollback_postcondition_and_audit_recorded",)
    payload: dict[str, Any] = {
        "report_id": "",
        "ledger_id": ledger.ledger_id,
        "transaction_id": ledger.transaction_id,
        "lifecycle_status": status,
        "present_event_kinds": present,
        "missing_event_kinds": tuple(missing),
        "orphan_codes": orphan_codes,
        "contradiction_codes": contradiction_codes,
        "closure_codes": closure_codes,
        "warning_codes": ledger.warning_codes,
        "risk_codes": ledger.risk_codes,
        "created_at": created_at or ledger.created_at,
        "digest": "",
        "metadata_only": True,
        "lifecycle_report_only": True,
        "performs_no_new_effect": True,
        "host_mutation_performed": False,
    }
    payload["report_id"] = _digest_id("local-effect-lifecycle-report-", payload)
    payload["digest"] = local_effect_transaction_lifecycle_report_digest(payload)
    return LocalEffectTransactionLifecycleReport(**payload)


def build_transaction_ledger_from_local_diagnostic_records(
    *,
    effect_request: Any | None = None,
    effect_result: Any | None = None,
    effect_receipt: Any | None = None,
    postcondition_check: Any | None = None,
    production_audit: Any | None = None,
    rollback_plan: Any | None = None,
    exact_rollback_request: Any | None = None,
    exact_rollback_result: Any | None = None,
    exact_rollback_receipt: Any | None = None,
    rollback_postcondition_check: Any | None = None,
    rollback_audit: Any | None = None,
    created_at: str = DEFAULT_CREATED_AT,
    allow_duplicate_event_kinds: bool = False,
) -> LocalEffectTransactionLedgerBundle:
    supplied = tuple(record for record in (effect_request, effect_result, effect_receipt, postcondition_check, production_audit, rollback_plan, exact_rollback_request, exact_rollback_result, exact_rollback_receipt, rollback_postcondition_check, rollback_audit) if record is not None)
    transaction_id = _transaction_id_from_records(supplied)
    entries: list[LocalEffectTransactionEntry] = []
    previous: str | None = None
    contradiction_sources: list[str] = []
    for event_kind, record, status, evidence in _entry_specs(
        effect_request=effect_request,
        effect_result=effect_result,
        effect_receipt=effect_receipt,
        postcondition_check=postcondition_check,
        production_audit=production_audit,
        rollback_plan=rollback_plan,
        exact_rollback_request=exact_rollback_request,
        exact_rollback_result=exact_rollback_result,
        exact_rollback_receipt=exact_rollback_receipt,
        rollback_postcondition_check=rollback_postcondition_check,
        rollback_audit=rollback_audit,
    ):
        codes = _contradiction_codes_for_record(event_kind, record)
        entry_status = "local_effect_transaction_contradicted" if codes else status
        entry = build_local_effect_transaction_entry(transaction_id=transaction_id, event_kind=event_kind, source_record=record, transaction_status=entry_status, previous_entry_digest=previous, evidence_summary=evidence, created_at=created_at)
        entries.append(entry)
        previous = entry.digest
        contradiction_sources.extend(codes)
    if contradiction_sources:
        marker = {"marker_id": "transaction-contradiction", "digest": hashlib.sha256("transaction-contradiction".encode("utf-8")).hexdigest(), "evidence_summary": tuple(contradiction_sources), "created_at": created_at}
        entries.append(build_local_effect_transaction_entry(transaction_id=transaction_id, event_kind="transaction_contradicted", source_record=marker, transaction_status="local_effect_transaction_contradicted", previous_entry_digest=previous, evidence_summary=contradiction_sources, created_at=created_at))
    ledger = build_local_effect_transaction_ledger(entries, transaction_id=transaction_id, created_at=created_at, allow_duplicate_event_kinds=allow_duplicate_event_kinds)
    report = build_local_effect_transaction_lifecycle_report(ledger, created_at=created_at)
    return LocalEffectTransactionLedgerBundle(ledger, report)


def validate_local_effect_transaction_entry(entry: LocalEffectTransactionEntry | Mapping[str, Any]) -> LocalEffectTransactionLedgerValidationResult:
    p = _source_payload(entry)
    findings: list[str] = []
    if p.get("event_kind") not in EVENT_KINDS:
        findings.append("unknown_event_kind")
    if p.get("transaction_status") not in TRANSACTION_STATUSES:
        findings.append("unknown_transaction_status")
    for flag in ("metadata_only", "ledger_entry_only", "performs_no_new_effect"):
        if not p.get(flag):
            findings.append(f"entry_missing_{flag}")
    for flag in ("host_mutation_performed", "file_delete_performed", "network_performed", "provider_invocation_performed", "prompt_assembly_performed", "subprocess_performed", "shell_performed"):
        if p.get(flag):
            findings.append(f"entry_forbidden_{flag}")
    if p.get("digest") != local_effect_transaction_entry_digest(p):
        findings.append("entry_digest_mismatch")
    return LocalEffectTransactionLedgerValidationResult(ok=not findings, findings=tuple(findings))


def validate_local_effect_transaction_ledger(ledger: LocalEffectTransactionLedger | Mapping[str, Any]) -> LocalEffectTransactionLedgerValidationResult:
    p = _source_payload(ledger)
    findings: list[str] = []
    if p.get("ledger_status") not in LEDGER_STATUSES:
        findings.append("unknown_ledger_status")
    if p.get("current_transaction_status") not in TRANSACTION_STATUSES:
        findings.append("unknown_current_transaction_status")
    for flag in ("metadata_only", "transaction_ledger_only", "performs_no_new_effect"):
        if not p.get(flag):
            findings.append(f"ledger_missing_{flag}")
    for flag in ("host_mutation_performed", "network_performed", "provider_invocation_performed", "prompt_assembly_performed"):
        if p.get(flag):
            findings.append(f"ledger_forbidden_{flag}")
    digest_payload = dict(p)
    digest_payload["entries"] = [entry.to_dict() if hasattr(entry, "to_dict") else dict(entry) for entry in p.get("entries", ())]
    if p.get("digest") != local_effect_transaction_ledger_digest(digest_payload):
        findings.append("ledger_digest_mismatch")
    return LocalEffectTransactionLedgerValidationResult(ok=not findings, findings=tuple(findings))


def validate_local_effect_transaction_lifecycle_report(report: LocalEffectTransactionLifecycleReport | Mapping[str, Any]) -> LocalEffectTransactionLedgerValidationResult:
    p = _source_payload(report)
    findings: list[str] = []
    if p.get("lifecycle_status") not in LIFECYCLE_STATUSES:
        findings.append("unknown_lifecycle_status")
    for flag in ("metadata_only", "lifecycle_report_only", "performs_no_new_effect"):
        if not p.get(flag):
            findings.append(f"report_missing_{flag}")
    if p.get("host_mutation_performed"):
        findings.append("report_forbidden_host_mutation")
    if p.get("digest") != local_effect_transaction_lifecycle_report_digest(p):
        findings.append("report_digest_mismatch")
    return LocalEffectTransactionLedgerValidationResult(ok=not findings, findings=tuple(findings))


def validate_local_effect_transaction_ledger_artifact_receipt(receipt: LocalEffectTransactionLedgerArtifactReceipt | Mapping[str, Any]) -> LocalEffectTransactionLedgerValidationResult:
    p = _source_payload(receipt)
    findings: list[str] = []
    if p.get("artifact_status") not in ARTIFACT_STATUSES:
        findings.append("unknown_artifact_status")
    for flag in ("metadata_only", "ledger_artifact_receipt_only"):
        if not p.get(flag):
            findings.append(f"artifact_receipt_missing_{flag}")
    for flag in ("network_performed", "provider_invocation_performed", "prompt_assembly_performed"):
        if p.get(flag):
            findings.append(f"artifact_receipt_forbidden_{flag}")
    if p.get("digest") != local_effect_transaction_ledger_artifact_receipt_digest(p):
        findings.append("artifact_receipt_digest_mismatch")
    return LocalEffectTransactionLedgerValidationResult(ok=not findings, findings=tuple(findings))


def _artifact_payload(ledger: LocalEffectTransactionLedger, report: LocalEffectTransactionLifecycleReport | None = None) -> dict[str, Any]:
    return {
        "metadata_only": True,
        "local_effect_transaction_ledger_artifact": True,
        "performs_no_new_effect": True,
        "ledger": ledger.to_dict(),
        "lifecycle_report": report.to_dict() if report else build_local_effect_transaction_lifecycle_report(ledger).to_dict(),
    }


def write_local_effect_transaction_ledger_artifact(
    ledger: LocalEffectTransactionLedger,
    output_path: str | Path,
    *,
    lifecycle_report: LocalEffectTransactionLifecycleReport | None = None,
    created_at: str | None = None,
    force: bool = False,
) -> LocalEffectTransactionLedgerArtifactReceipt:
    path = Path(output_path).expanduser()
    if not str(output_path) or path == Path(path.anchor) or path.resolve() == Path(path.anchor).resolve():
        raise ValueError("refusing unsafe ledger artifact output path")
    if path.exists() and path.is_dir():
        raise ValueError("ledger artifact output path must be a file, not a directory")
    if path.exists() and not force:
        raise FileExistsError("ledger artifact already exists; pass --force to overwrite")
    content = json.dumps(_artifact_payload(ledger, lifecycle_report), indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    encoded = content.encode("utf-8")
    artifact_digest = hashlib.sha256(encoded).hexdigest()
    payload: dict[str, Any] = {
        "receipt_id": "",
        "ledger_id": ledger.ledger_id,
        "output_path": str(path),
        "artifact_digest": artifact_digest,
        "byte_count": len(encoded),
        "artifact_status": "local_effect_transaction_ledger_artifact_written" if ledger.ledger_status == "local_effect_transaction_ledger_current" else ("local_effect_transaction_ledger_artifact_contradicted" if ledger.ledger_status == "local_effect_transaction_ledger_contradicted" else "local_effect_transaction_ledger_artifact_incomplete"),
        "warning_codes": ledger.warning_codes,
        "risk_codes": tuple(sorted(set(ledger.risk_codes + ("explicit_local_ledger_artifact_write",)))),
        "created_at": created_at or ledger.created_at,
        "digest": "",
        "metadata_only": True,
        "ledger_artifact_receipt_only": True,
        "local_file_write_performed": True,
        "host_mutation_performed": True,
        "network_performed": False,
        "provider_invocation_performed": False,
        "prompt_assembly_performed": False,
    }
    payload["receipt_id"] = _digest_id("local-effect-ledger-artifact-receipt-", payload)
    payload["digest"] = local_effect_transaction_ledger_artifact_receipt_digest(payload)
    return LocalEffectTransactionLedgerArtifactReceipt(**payload)


def summarize_local_effect_transaction_entry(entry: LocalEffectTransactionEntry | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(entry)
    return {k: p.get(k) for k in ("entry_id", "transaction_id", "event_kind", "source_record_id", "source_record_digest", "previous_entry_digest", "transaction_status", "output_path", "artifact_digest", "metadata_only", "performs_no_new_effect", "host_mutation_performed", "file_delete_performed", "digest")}


def summarize_local_effect_transaction_ledger(ledger: LocalEffectTransactionLedger | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(ledger)
    return {k: p.get(k) for k in ("ledger_id", "transaction_id", "ledger_status", "current_transaction_status", "effect_receipt_id", "postcondition_check_id", "production_audit_id", "rollback_plan_id", "rollback_receipt_id", "rollback_postcondition_check_id", "rollback_audit_id", "open_issue_codes", "metadata_only", "performs_no_new_effect", "host_mutation_performed", "digest")}


def summarize_local_effect_transaction_lifecycle_report(report: LocalEffectTransactionLifecycleReport | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(report)
    return {k: p.get(k) for k in ("report_id", "ledger_id", "transaction_id", "lifecycle_status", "present_event_kinds", "missing_event_kinds", "orphan_codes", "contradiction_codes", "closure_codes", "metadata_only", "performs_no_new_effect", "host_mutation_performed", "digest")}


def summarize_local_effect_transaction_ledger_artifact_receipt(receipt: LocalEffectTransactionLedgerArtifactReceipt | Mapping[str, Any]) -> dict[str, Any]:
    p = _source_payload(receipt)
    return {k: p.get(k) for k in ("receipt_id", "ledger_id", "output_path", "artifact_digest", "byte_count", "artifact_status", "metadata_only", "local_file_write_performed", "host_mutation_performed", "network_performed", "provider_invocation_performed", "prompt_assembly_performed", "digest")}
