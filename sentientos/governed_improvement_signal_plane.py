"""Governed local improvement signal plane.

Normalizes repository-local evidence into a deterministic batch and routes it
into proposal-only improvement machinery.  This module performs no provider,
network, Git, Codex workspace, adoption, or repository source mutation effects.
"""
from __future__ import annotations

import hashlib, json, os, re, tempfile, xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from codex.gap_seeker import CoverageReader, GapReporter, RepoScanner, GapSignal

ALLOWED_SOURCES = {"run_tests","junit","coverage","mypy","covenant","telemetry","capability_gap","gap_seeker","model_observation"}
GENESIS_KINDS = {"missing_capability","new_flow","uncovered_flow","capability_gap","telemetry_gap"}
SPEC_KINDS = {"test_failure","mypy_error","type_error","recurring_failure","covenant_failure","typing_failure"}
DIAGNOSTIC_KINDS = {"todo","fixme","unimplemented","coverage_gap","missing_tests","diagnostic"}
MAX_RECORDS = 512
MAX_BYTES = 2_000_000
RUN_TESTS_PROVENANCE_RELATIVE_PATH = "glow/test_runs/test_run_provenance.json"
RUN_TESTS_REQUIRED_FIELDS = ("schema_version","pytest_exit_code","tests_selected","tests_executed","tests_passed","tests_failed","metrics_status","exit_reason","junitxml_path","failure_report_path","git_sha","provenance_hash","prev_provenance_hash")


def _sha(data: bytes) -> str: return "sha256:" + hashlib.sha256(data).hexdigest()
def _stable_json(obj: Any) -> str: return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
def _sid(payload: Mapping[str, Any]) -> str: return "gis-" + hashlib.sha256(_stable_json(payload).encode()).hexdigest()[:24]


def canonical_repo_path(value: str | None, repo_root: Path | str = Path.cwd(), *, allow_external: bool = False) -> str | None:
    if value in (None, ""):
        return None
    p = Path(str(value))
    root = Path(repo_root).resolve()
    if p.is_absolute():
        resolved = p.resolve()
        try:
            return resolved.relative_to(root).as_posix()
        except ValueError as exc:
            if allow_external:
                return "external:" + resolved.as_posix()
            raise ValueError(f"absolute_path_outside_repo:{value}") from exc
    if ".." in p.parts:
        raise ValueError(f"path_traversal:{value}")
    return p.as_posix()


@dataclass(frozen=True)
class ImprovementSignal:
    signal_id: str
    source_kind: str
    finding_kind: str
    severity: str
    description: str
    subject_path: str | None = None
    spec_id: str | None = None
    capability_id: str | None = None
    telemetry_stream: str | None = None
    source_artifact: str | None = None
    source_digest: str | None = None
    evidence_refs: tuple[str, ...] = ()
    declared_validation_expectations: tuple[str, ...] = ()
    requested_authority_classes: tuple[str, ...] = ()
    declared_constraints: tuple[str, ...] = ()
    estimated_file_count: int = 1
    estimated_changed_line_count: int = 1
    estimated_implementation_seconds: int = 60
    estimated_validation_seconds: int = 60
    observed_at: str | None = None
    routing_eligible: bool = True
    reason_codes: tuple[str, ...] = ()
    adoption_performed: bool = False
    repository_mutation_performed: bool = False
    provider_or_network_or_git_operation_performed: bool = False
    trial_performed: bool = False
    def semantic_payload(self) -> dict[str, Any]:
        d = asdict(self)
        for k in ("signal_id", "observed_at", "source_artifact"):
            d.pop(k, None)
        return d
    def to_dict(self) -> dict[str, Any]: return asdict(self)


@dataclass(frozen=True)
class RoutingReceipt:
    signal_id: str
    evidence_digest: str
    disposition: str
    target: str | None
    reason_codes: tuple[str, ...]
    required_downstream_review: str
    candidate_identified: bool = False
    proposal_generation_attempted: bool = False
    proposal_generation_occurred: bool = False
    proposal_id: str | None = None
    trial_occurred: bool = False
    trial_passed: bool | None = None
    pending_review: bool = False
    adoption_occurred: bool = False
    repository_mutation_occurred: bool = False
    provider_network_git_operation_occurred: bool = False
    def to_dict(self) -> dict[str, Any]: return asdict(self)


@dataclass(frozen=True)
class SignalBatch:
    batch_id: str
    batch_digest: str
    signals: tuple[ImprovementSignal, ...]
    duplicate_signal_ids: tuple[str, ...] = ()
    contradiction_ids: tuple[str, ...] = ()
    invalid_reasons: tuple[str, ...] = ()
    input_counts_by_source: Mapping[str, int] | None = None
    no_op: bool = False
    def to_dict(self) -> dict[str, Any]:
        return {"schema":"governed_improvement_signal_batch:v1","batch_id":self.batch_id,"batch_digest":self.batch_digest,"signals":[s.to_dict() for s in self.signals],"duplicate_signal_ids":list(self.duplicate_signal_ids),"contradiction_ids":list(self.contradiction_ids),"invalid_reasons":list(self.invalid_reasons),"input_counts_by_source":dict(self.input_counts_by_source or {}),"no_op":self.no_op}


@dataclass(frozen=True)
class SignalPlaneEvaluation:
    batch: SignalBatch
    receipts: tuple[RoutingReceipt, ...]
    summary: Mapping[str, Any]
    genesis_inputs: Mapping[str, Any]
    amendment_inputs: tuple[Mapping[str, Any], ...]
    def to_dict(self) -> dict[str, Any]:
        return {"schema":"governed_improvement_signal_plane_evaluation:v1","batch":self.batch.to_dict(),"receipts":[r.to_dict() for r in self.receipts],"summary":dict(self.summary),"genesis_inputs":dict(self.genesis_inputs),"amendment_inputs":[dict(x) for x in self.amendment_inputs]}


def normalize_record(record: Mapping[str, Any], *, repo_root: Path | str = Path.cwd()) -> ImprovementSignal:
    src = str(record.get("source_kind") or record.get("source") or "").strip()
    kind = str(record.get("finding_kind") or record.get("kind") or "").strip()
    reasons = []
    if src not in ALLOWED_SOURCES: reasons.append("unknown_source_kind")
    for f in ("adoption_performed","repository_mutation_performed","provider_or_network_or_git_operation_performed","trial_performed"):
        if bool(record.get(f)): reasons.append(f"false_authority_claim:{f}")
    path = canonical_repo_path(record.get("subject_path") or record.get("path"), repo_root)
    artifact = canonical_repo_path(record.get("source_artifact") or record.get("artifact"), repo_root, allow_external=True)
    payload: dict[str, Any] = {"source_kind":src,"finding_kind":kind,"severity":str(record.get("severity","medium")),"description":str(record.get("description") or record.get("message") or kind or src),"subject_path":path,"spec_id":record.get("spec_id"),"capability_id":record.get("capability_id"),"telemetry_stream":record.get("telemetry_stream"),"source_artifact":artifact,"source_digest":record.get("source_digest"),"evidence_refs":tuple(sorted(str(x) for x in record.get("evidence_refs", ()) or ())),"declared_validation_expectations":tuple(sorted(str(x) for x in record.get("declared_validation_expectations", ()) or ())),"requested_authority_classes":tuple(sorted(str(x) for x in record.get("requested_authority_classes", ()) or ())),"declared_constraints":tuple(sorted(str(x) for x in record.get("declared_constraints", ()) or ())),"estimated_file_count":int(record.get("estimated_file_count",1)),"estimated_changed_line_count":int(record.get("estimated_changed_line_count",1)),"estimated_implementation_seconds":int(record.get("estimated_implementation_seconds",60)),"estimated_validation_seconds":int(record.get("estimated_validation_seconds",60)),"routing_eligible":not reasons,"reason_codes":tuple(sorted(reasons)),"adoption_performed":False,"repository_mutation_performed":False,"provider_or_network_or_git_operation_performed":False,"trial_performed":False}
    semantic = dict(payload); semantic.pop("source_artifact", None)
    return ImprovementSignal(signal_id=_sid(semantic), observed_at=record.get("observed_at"), **payload)


def _record_from_gap(g: GapSignal) -> dict[str, Any]:
    kind = "mypy_error" if g.source == "mypy" else g.kind
    src = "mypy" if g.source == "mypy" else ("coverage" if g.source == "coverage" else "gap_seeker")
    return {"source_kind": src, "finding_kind": kind, "severity": g.severity, "description": g.description, "subject_path": g.path.as_posix(), "evidence_refs": [f"line:{g.line}"], "spec_id": g.metadata.get("spec_id")}


def _read_once(path: Path, *, expected_digest: str | None = None) -> tuple[bytes, str]:
    data = path.read_bytes()
    if len(data) > MAX_BYTES: raise ValueError("oversized_input")
    digest = _sha(data)
    if expected_digest and expected_digest != digest: raise ValueError("source_digest_mismatch")
    return data, digest


def records_from_artifact(source_kind: str, path: Path | str, *, repo_root: Path | str = Path.cwd(), expected_digest: str | None = None) -> list[dict[str, Any]]:
    p = Path(path); data, digest = _read_once(p, expected_digest=expected_digest)
    text = data.decode("utf-8", errors="replace")
    artifact = str(p)
    if source_kind == "coverage":
        gaps = CoverageReader().collect(coverage_report=json.loads(text))
        return [{**_record_from_gap(g), "source_artifact": artifact, "source_digest": digest} for g in gaps]
    if source_kind == "mypy":
        gaps = CoverageReader().collect(mypy_output=text)
        return [{**_record_from_gap(g), "source_artifact": artifact, "source_digest": digest} for g in gaps]
    if source_kind == "junit":
        root = ET.fromstring(text); out=[]
        for case in root.findall(".//testcase"):
            failure = case.find("failure") or case.find("error")
            if failure is not None:
                out.append({"source_kind":"junit","finding_kind":"test_failure","severity":"high","description":failure.get("message") or (failure.text or "junit failure"),"subject_path":case.get("file") or case.get("classname","tests"),"spec_id":case.get("classname") or case.get("name"),"source_artifact":artifact,"source_digest":digest})
        return out
    payload = json.loads(text)
    if source_kind == "run_tests":
        return records_from_run_tests_provenance(payload, provenance_path=p, repo_root=repo_root, provenance_digest=digest)
    if source_kind in {"covenant","telemetry","capability_gap","model_observation"}:
        records = payload.get("signals") or payload.get("findings") or payload.get("observations") or payload
        if isinstance(records, Mapping): records=[records]
        return [{**dict(r), "source_kind": source_kind, "source_artifact": artifact, "source_digest": digest} for r in records if isinstance(r, Mapping)]
    raise ValueError(f"unknown_artifact_source:{source_kind}")



def _resolve_linked_artifact(value: object, *, provenance_path: Path, repo_root: Path) -> Path | None:
    if value in (None, ""):
        return None
    p = Path(str(value))
    resolved = (p if p.is_absolute() else repo_root / p).resolve()
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError(f"linked_artifact_outside_repo:{value}") from exc
    return resolved


def _failure_group_records(groups: Sequence[Mapping[str, Any]], *, artifact: str, artifact_digest: str, provenance_digest: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, group in enumerate(groups):
        nodeid = str(group.get("nodeid") or group.get("node_id") or group.get("test_id") or group.get("name") or f"failure_group_{idx}")
        file_value = group.get("file") or group.get("path") or (nodeid.split("::", 1)[0] if "::" in nodeid else "tests")
        message = str(group.get("message") or group.get("exception_message") or group.get("summary") or nodeid)
        meta = {
            "failure_group_index": idx,
            "failure_class": group.get("failure_class") or group.get("class"),
            "exception_type": group.get("exception_type"),
            "nodeid": nodeid,
            "message": message,
            "file": file_value,
            "line": group.get("line"),
            "count": group.get("count", 1),
            "provenance_digest": provenance_digest,
        }
        out.append({
            "source_kind": "run_tests",
            "finding_kind": "test_failure",
            "severity": "high",
            "description": message,
            "subject_path": file_value,
            "spec_id": nodeid,
            "source_artifact": artifact,
            "source_digest": artifact_digest,
            "evidence_refs": [f"failure_group:{idx}", f"failure_class:{meta['failure_class']}", f"count:{meta['count']}"],
        })
    return out


def records_from_run_tests_provenance(payload: Mapping[str, Any], *, provenance_path: Path, repo_root: Path | str = Path.cwd(), provenance_digest: str | None = None) -> list[dict[str, Any]]:
    root = Path(repo_root).resolve()
    missing = [field for field in RUN_TESTS_REQUIRED_FIELDS if field not in payload]
    if missing:
        raise ValueError("run_tests_provenance_missing_fields:" + ",".join(missing))
    tests_failed = int(payload.get("tests_failed") or 0)
    if tests_failed <= 0:
        return []
    failure_path = _resolve_linked_artifact(payload.get("failure_report_path"), provenance_path=provenance_path, repo_root=root)
    junit_path = _resolve_linked_artifact(payload.get("junitxml_path"), provenance_path=provenance_path, repo_root=root)
    groups: list[Mapping[str, Any]] = []
    artifact_path = failure_path or junit_path
    if failure_path and failure_path.exists():
        failure_data, failure_digest = _read_once(failure_path)
        failure_payload = json.loads(failure_data.decode("utf-8"))
        raw_groups = failure_payload.get("failure_groups") if isinstance(failure_payload, Mapping) else None
        if not isinstance(raw_groups, list):
            raise ValueError("failure_digest_missing_failure_groups")
        groups = [g for g in raw_groups if isinstance(g, Mapping)]
        artifact = failure_path.as_posix()
        artifact_digest = failure_digest
    elif junit_path and junit_path.exists():
        junit_data, junit_digest = _read_once(junit_path)
        junit_root = ET.fromstring(junit_data.decode("utf-8", errors="replace"))
        for case in junit_root.findall(".//testcase"):
            failure = case.find("failure") or case.find("error")
            if failure is not None:
                groups.append({"nodeid": f"{case.get('classname','tests')}::{case.get('name','test')}", "file": case.get("file") or case.get("classname", "tests"), "message": failure.get("message") or failure.text or "junit failure", "exception_type": failure.get("type"), "failure_class": "junit_failure", "line": case.get("line"), "count": 1})
        artifact = junit_path.as_posix()
        artifact_digest = junit_digest
    else:
        raise ValueError("run_tests_failure_evidence_missing")
    if not groups:
        raise ValueError("run_tests_failure_groups_empty")
    return _failure_group_records(groups, artifact=artifact, artifact_digest=artifact_digest, provenance_digest=provenance_digest or _sha(_stable_json(payload).encode()))

def collect_repository_evidence(*, repo_root: Path | str = Path.cwd(), artifacts: Sequence[Mapping[str, Any]] = (), direct_records: Sequence[Mapping[str, Any]] = (), scan_repo: bool = False) -> list[ImprovementSignal]:
    records: list[Mapping[str, Any]] = []
    total_direct = len(_stable_json(list(direct_records)).encode())
    if total_direct > MAX_BYTES: raise ValueError("oversized_direct_input")
    records.extend(direct_records)
    artifact_list = list(artifacts)
    default_run_tests = Path(repo_root) / RUN_TESTS_PROVENANCE_RELATIVE_PATH
    if not artifact_list and default_run_tests.exists():
        artifact_list.append({"source_kind":"run_tests", "path": default_run_tests.as_posix()})
    for artifact in artifact_list:
        records.extend(records_from_artifact(str(artifact.get("source_kind")), Path(str(artifact.get("path"))), repo_root=repo_root, expected_digest=artifact.get("source_digest")))
    if scan_repo:
        gaps = GapReporter().aggregate(RepoScanner(repo_root).iter_gaps())
        records.extend(_record_from_gap(g) for g in gaps[:MAX_RECORDS])
    if len(records) > MAX_RECORDS: raise ValueError("too_many_records")
    return [normalize_record(r, repo_root=repo_root) for r in records]


def load_json_records(paths: Sequence[Path | str], *, repo_root: Path | str = Path.cwd()) -> list[ImprovementSignal]:
    out: list[ImprovementSignal] = []
    for path in paths:
        p = Path(path); data,digest = _read_once(p); payload = json.loads(data.decode())
        records = payload.get("signals") if isinstance(payload, dict) else payload
        if isinstance(records, dict): records = [records]
        for rec in records or []:
            if not isinstance(rec, Mapping): raise ValueError("malformed_record")
            out.append(normalize_record({**dict(rec), "source_artifact": str(p), "source_digest": digest}, repo_root=repo_root))
            if len(out) > MAX_RECORDS: raise ValueError("too_many_records")
    return out


def build_batch(records: Iterable[Mapping[str, Any]] | Iterable[ImprovementSignal], *, repo_root: Path | str = Path.cwd()) -> SignalBatch:
    signals = [r if isinstance(r, ImprovementSignal) else normalize_record(r, repo_root=repo_root) for r in records]
    signals.sort(key=lambda s: (s.signal_id, s.source_kind, s.finding_kind))
    seen: dict[str, ImprovementSignal] = {}
    dup: list[str] = []
    contradictions: list[str] = []
    counts: dict[str, int] = {}
    unique: list[ImprovementSignal] = []
    by_subject: dict[tuple[str, str, str | None, str | None, str | None, str | None], ImprovementSignal] = {}
    invalid: list[str] = []
    for s in signals:
        expected = _sid(s.semantic_payload())
        if expected != s.signal_id: invalid.append("signal_id_mismatch")
        counts[s.source_kind]=counts.get(s.source_kind,0)+1; invalid.extend(s.reason_codes)
        if s.signal_id in seen: dup.append(s.signal_id); continue
        key=(s.source_kind,s.finding_kind,s.subject_path,s.spec_id,s.capability_id,s.telemetry_stream)
        prev=by_subject.get(key)
        if prev and (prev.description != s.description or prev.severity != s.severity): contradictions.extend([prev.signal_id,s.signal_id])
        by_subject[key]=s; seen[s.signal_id]=s; unique.append(s)
    body=[s.semantic_payload() for s in unique]; digest=_sha(_stable_json({"signals": body, "duplicates": sorted(set(dup)), "contradictions": sorted(set(contradictions))}).encode())
    return SignalBatch("gisb-"+hashlib.sha256(digest.encode()).hexdigest()[:24], digest, tuple(unique), tuple(sorted(set(dup))), tuple(sorted(set(contradictions))), tuple(sorted(set(invalid))), counts, no_op=not unique)


def route_batch(batch: SignalBatch) -> tuple[RoutingReceipt, ...]:
    if batch.no_op:
        return (RoutingReceipt("batch-noop", batch.batch_digest, "no_op", None, ("empty_input",), "none"),)
    receipts=[]
    for s in batch.signals:
        reasons=list(s.reason_codes); disposition="diagnostic_only"; target=s.subject_path or s.spec_id or s.capability_id; review="operator_review_required"; candidate=False
        if not s.routing_eligible or reasons or s.signal_id in batch.contradiction_ids:
            disposition="blocked_invalid"; reasons.append("invalid_or_contradicted"); review="manual_triage_required"
        elif s.finding_kind in GENESIS_KINDS and (s.capability_id or s.telemetry_stream):
            disposition="genesis_proposal_candidate"; target=s.capability_id or s.telemetry_stream; candidate=True; reasons.append("missing_capability_or_new_flow")
        elif s.finding_kind in SPEC_KINDS and s.spec_id:
            disposition="spec_amendment_candidate"; target=s.spec_id; candidate=True; reasons.append("existing_spec_recurring_failure")
        elif s.finding_kind in DIAGNOSTIC_KINDS:
            disposition="gap_seeker_diagnostic"; reasons.append("gap_seeker_supported_diagnostic")
        else:
            disposition="blocked_invalid"; reasons.append("no_safe_route")
        receipts.append(RoutingReceipt(s.signal_id, s.source_digest or batch.batch_digest, disposition, target, tuple(sorted(set(reasons))), review, candidate_identified=candidate))
    return tuple(sorted(receipts, key=lambda r: r.signal_id))


def evaluate_signal_plane(records: Iterable[Mapping[str, Any]] | Iterable[ImprovementSignal] = (), *, repo_root: Path | str = Path.cwd()) -> SignalPlaneEvaluation:
    batch=build_batch(records, repo_root=repo_root); receipts=route_batch(batch); counts: dict[str, int]={}
    for r in receipts: counts[r.disposition]=counts.get(r.disposition,0)+1
    lookup={s.signal_id:s for s in batch.signals}; genesis=[]; amendments=[]
    for r in receipts:
        s=lookup.get(r.signal_id)
        if not s: continue
        if r.disposition=="genesis_proposal_candidate": genesis.append(s)
        if r.disposition=="spec_amendment_candidate": amendments.append({"spec_id":s.spec_id,"signal_type":s.finding_kind,"signal_id":s.signal_id,"batch_id":batch.batch_id,"source_digest":s.source_digest,"routing_receipt":r.to_dict(),"metadata":s.to_dict()})
    summary={"batch_id":batch.batch_id,"batch_digest":batch.batch_digest,"input_counts_by_source":dict(batch.input_counts_by_source or {}),"routed_counts_by_disposition":counts,"proposal_count":0,"blocked_invalid_count":counts.get("blocked_invalid",0),"degraded": bool(batch.invalid_reasons or batch.contradiction_ids),"no_op":batch.no_op,"adoption_performed":False,"repository_mutation_performed":False,"provider_network_git_operation_performed":False}
    genesis_inputs={"batch_id":batch.batch_id,"telemetry_streams":[{"name":s.telemetry_stream or s.capability_id or s.signal_id,"capability":s.capability_id or s.telemetry_stream or s.signal_id,"description":s.description,"sample_payload":{"signal_id":s.signal_id,"batch_id":batch.batch_id,"source_digest":s.source_digest}} for s in genesis],"vows":[{"capability":s.capability_id or s.telemetry_stream or s.signal_id,"description":"proposal-only review required"} for s in genesis]}
    return SignalPlaneEvaluation(batch, receipts, summary, genesis_inputs, tuple(amendments))


def atomic_write_json(path: Path | str, payload: Mapping[str, Any]) -> None:
    p=Path(path); p.parent.mkdir(parents=True, exist_ok=True); data=json.dumps(payload, sort_keys=True, indent=2).encode()+b"\n"; fd,tmp=tempfile.mkstemp(prefix=p.name+".", dir=str(p.parent))
    with os.fdopen(fd,"wb") as f: f.write(data)
    os.replace(tmp,p)


def persist_runtime_artifacts(root: Path | str, evaluation: SignalPlaneEvaluation, *, tick_id: str) -> dict[str, str]:
    base=Path(root)/"governed_improvement_signal_plane"/re.sub(r"[^A-Za-z0-9_.-]+","_",tick_id); base.mkdir(parents=True, exist_ok=True)
    paths={"batch":base/"batch.json", "routing":base/"routing.json", "evaluation":base/"evaluation.json", "manifest":base/"manifest.json"}
    atomic_write_json(paths["batch"], evaluation.batch.to_dict()); atomic_write_json(paths["routing"], {"receipts":[r.to_dict() for r in evaluation.receipts]}); atomic_write_json(paths["evaluation"], evaluation.to_dict())
    manifest = {
        "schema": "governed_improvement_signal_plane_manifest:v1",
        "artifacts": {
            name: {"path": str(path), "digest": _sha(path.read_bytes())}
            for name, path in paths.items()
            if name != "manifest"
        },
    }
    atomic_write_json(paths["manifest"], manifest)
    return {k: str(v) for k,v in paths.items()}


def render_markdown(e: SignalPlaneEvaluation) -> str:
    lines=["# Governed Improvement Signal Plane", "", f"- Batch: `{e.batch.batch_id}`", f"- Digest: `{e.batch.batch_digest}`", f"- No-op: `{str(e.batch.no_op).lower()}`", "- Adoption performed: `false`", "- Repository mutation performed: `false`", "", "## Routing"]
    for r in e.receipts: lines.append(f"- `{r.signal_id}` → `{r.disposition}` ({', '.join(r.reason_codes)})")
    return "\n".join(lines)+"\n"


def validate_evaluation(payload: Mapping[str, Any]) -> tuple[bool, tuple[str,...]]:
    reasons=[]
    if payload.get("schema") != "governed_improvement_signal_plane_evaluation:v1": reasons.append("wrong_schema")
    raw_batch_payload = payload.get("batch")
    batch_payload = raw_batch_payload if isinstance(raw_batch_payload, Mapping) else {}
    raw_signal_rows = batch_payload.get("signals")
    signal_rows = raw_signal_rows if isinstance(raw_signal_rows, list) else []
    try:
        signals = [ImprovementSignal(**dict(row)) for row in signal_rows if isinstance(row, Mapping)]
        rebuilt = build_batch(signals)
        if rebuilt.batch_digest != batch_payload.get("batch_digest"):
            reasons.append("batch_digest_mismatch")
        if rebuilt.batch_id != batch_payload.get("batch_id"):
            reasons.append("batch_id_mismatch")
        if tuple(batch_payload.get("duplicate_signal_ids", ())) != rebuilt.duplicate_signal_ids:
            reasons.append("duplicate_set_mismatch")
        if tuple(batch_payload.get("contradiction_ids", ())) != rebuilt.contradiction_ids:
            reasons.append("contradiction_set_mismatch")
        expected_receipts = [r.to_dict() for r in route_batch(rebuilt)]
        if _stable_json(expected_receipts) != _stable_json(payload.get("receipts")):
            reasons.append("routing_receipt_mismatch")
        expected_evaluation = evaluate_signal_plane(signals)
        expected_summary = expected_evaluation.summary
        raw_summary_for_counts = payload.get("summary")
        summary_for_counts: Mapping[str, Any] = raw_summary_for_counts if isinstance(raw_summary_for_counts, Mapping) else {}
        for key, value in expected_summary.items():
            if summary_for_counts.get(key) != value:
                reasons.append(f"summary_mismatch:{key}")
        if payload.get("genesis_inputs") != expected_evaluation.genesis_inputs:
            reasons.append("genesis_inputs_mismatch")
        # JSON-loaded evaluations contain lists where the in-memory routing
        # receipt dataclass projects tuples. Compare their canonical JSON
        # domains so a persisted canonical evaluation remains valid.
        if _stable_json(payload.get("amendment_inputs")) != _stable_json([dict(x) for x in expected_evaluation.amendment_inputs]):
            reasons.append("amendment_inputs_mismatch")
        for row in signal_rows:
            if isinstance(row, Mapping) and row.get("source_digest") and not str(row.get("source_digest")).startswith("sha256:"):
                reasons.append("source_digest_invalid")
    except Exception as exc:
        reasons.append(f"structural_validation_failed:{exc.__class__.__name__}")
    raw_summary = payload.get("summary")
    summary: Mapping[str, Any] = raw_summary if isinstance(raw_summary, Mapping) else {}
    for key in ("adoption_performed","repository_mutation_performed","provider_network_git_operation_performed"):
        if summary.get(key) is not False: reasons.append(f"authority_claim_present:{key}")
    for receipt in payload.get("receipts", []) if isinstance(payload.get("receipts"), list) else []:
        if isinstance(receipt, Mapping) and (receipt.get("adoption_occurred") or receipt.get("repository_mutation_occurred") or receipt.get("provider_network_git_operation_occurred")):
            reasons.append("receipt_authority_claim_present")
    return (not reasons, tuple(sorted(set(reasons))))
