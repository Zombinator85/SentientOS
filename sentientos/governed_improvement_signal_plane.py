"""Governed local improvement signal plane.

Normalizes repository-local evidence into a deterministic batch and routes it
into proposal-only improvement machinery.  This module performs no provider,
network, Git, Codex workspace, adoption, or repository source mutation effects.
"""
from __future__ import annotations

import hashlib, json, os, re, tempfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ALLOWED_SOURCES = {"run_tests","junit","coverage","mypy","covenant","telemetry","capability_gap","gap_seeker","model_observation"}
AUTHORITY_FIELDS = ("adoption_performed","repository_mutation_performed","provider_or_network_or_git_operation_performed","trial_performed")
GENESIS_KINDS = {"missing_capability","new_flow","uncovered_flow","capability_gap","telemetry_gap"}
SPEC_KINDS = {"test_failure","mypy_error","recurring_failure","covenant_failure","typing_failure"}
DIAGNOSTIC_KINDS = {"todo","fixme","unimplemented","coverage_gap","missing_tests","diagnostic"}
MAX_RECORDS = 512
MAX_BYTES = 2_000_000


def _sha(data: bytes) -> str: return "sha256:" + hashlib.sha256(data).hexdigest()
def _stable_json(obj: Any) -> str: return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "root"


def canonical_repo_path(value: str | None, repo_root: Path | str = Path.cwd()) -> str | None:
    if value in (None, ""):
        return None
    p = Path(str(value))
    if p.is_absolute():
        try:
            p = p.resolve().relative_to(Path(repo_root).resolve())
        except Exception as exc:
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
    observed_at: str | None = None
    routing_eligible: bool = True
    reason_codes: tuple[str, ...] = ()
    adoption_performed: bool = False
    repository_mutation_performed: bool = False
    provider_or_network_or_git_operation_performed: bool = False
    trial_performed: bool = False

    def semantic_payload(self) -> dict[str, Any]:
        d = asdict(self); d.pop("signal_id", None); return d
    def to_dict(self) -> dict[str, Any]: return asdict(self)


@dataclass(frozen=True)
class RoutingReceipt:
    signal_id: str
    evidence_digest: str
    disposition: str
    target: str | None
    reason_codes: tuple[str, ...]
    required_downstream_review: str
    proposal_generation_occurred: bool = False
    trial_occurred: bool = False
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
    def to_dict(self) -> dict[str, Any]:
        return {"schema":"governed_improvement_signal_batch:v1","batch_id":self.batch_id,"batch_digest":self.batch_digest,"signals":[s.to_dict() for s in self.signals],"duplicate_signal_ids":list(self.duplicate_signal_ids),"contradiction_ids":list(self.contradiction_ids),"invalid_reasons":list(self.invalid_reasons),"input_counts_by_source":dict(self.input_counts_by_source or {})}


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
    for f in ("adoption_performed","repository_mutation_performed","provider_or_network_or_git_operation_performed"):
        if bool(record.get(f)): reasons.append(f"false_authority_claim:{f}")
    path = canonical_repo_path(record.get("subject_path") or record.get("path"), repo_root)
    artifact = canonical_repo_path(record.get("source_artifact") or record.get("artifact"), repo_root)
    digest = record.get("source_digest")
    evidence_refs = tuple(sorted(str(x) for x in record.get("evidence_refs", ()) or ()))
    payload: dict[str, Any] = {"source_kind":src,"finding_kind":kind,"severity":str(record.get("severity","medium")),"description":str(record.get("description") or record.get("message") or kind or src),"subject_path":path,"spec_id":record.get("spec_id"),"capability_id":record.get("capability_id"),"telemetry_stream":record.get("telemetry_stream"),"source_artifact":artifact,"source_digest":digest,"evidence_refs":evidence_refs,"observed_at":record.get("observed_at"),"routing_eligible":not reasons,"reason_codes":tuple(sorted(reasons)),"adoption_performed":False,"repository_mutation_performed":False,"provider_or_network_or_git_operation_performed":False,"trial_performed":False}
    sid = "gis-" + hashlib.sha256(_stable_json(payload).encode()).hexdigest()[:24]
    return ImprovementSignal(
        signal_id=sid,
        source_kind=str(payload["source_kind"]),
        finding_kind=str(payload["finding_kind"]),
        severity=str(payload["severity"]),
        description=str(payload["description"]),
        subject_path=payload.get("subject_path"),
        spec_id=payload.get("spec_id"),
        capability_id=payload.get("capability_id"),
        telemetry_stream=payload.get("telemetry_stream"),
        source_artifact=payload.get("source_artifact"),
        source_digest=payload.get("source_digest"),
        evidence_refs=tuple(payload["evidence_refs"]),
        observed_at=payload.get("observed_at"),
        routing_eligible=bool(payload["routing_eligible"]),
        reason_codes=tuple(payload["reason_codes"]),
    )


def load_json_records(paths: Sequence[Path | str], *, repo_root: Path | str = Path.cwd()) -> list[ImprovementSignal]:
    out: list[ImprovementSignal] = []
    total = 0
    for path in paths:
        p = Path(path); data = p.read_bytes(); total += len(data)
        if total > MAX_BYTES: raise ValueError("oversized_input")
        digest = _sha(data); payload = json.loads(data.decode())
        records = payload.get("signals") if isinstance(payload, dict) else payload
        if isinstance(records, dict): records = [records]
        for rec in records or []:
            if not isinstance(rec, Mapping): raise ValueError("malformed_record")
            enriched = dict(rec); enriched.setdefault("source_artifact", str(p)); enriched.setdefault("source_digest", digest)
            out.append(normalize_record(enriched, repo_root=repo_root))
            if len(out) > MAX_RECORDS: raise ValueError("too_many_records")
    return out


def build_batch(records: Iterable[Mapping[str, Any]] | Iterable[ImprovementSignal], *, repo_root: Path | str = Path.cwd()) -> SignalBatch:
    signals = [r if isinstance(r, ImprovementSignal) else normalize_record(r, repo_root=repo_root) for r in records]
    signals.sort(key=lambda s: (s.signal_id, s.source_kind, s.finding_kind))
    seen: dict[str, ImprovementSignal] = {}; dup=[]; contradictions=[]; counts: dict[str,int]={}; unique=[]
    by_subject: dict[tuple[Any,...], ImprovementSignal] = {}
    invalid: list[str] = []
    for s in signals:
        counts[s.source_kind]=counts.get(s.source_kind,0)+1
        invalid.extend(s.reason_codes)
        if s.signal_id in seen: dup.append(s.signal_id); continue
        key=(s.source_kind,s.finding_kind,s.subject_path,s.spec_id,s.capability_id,s.telemetry_stream)
        prev=by_subject.get(key)
        if prev and (prev.description != s.description or prev.severity != s.severity):
            contradictions.extend(sorted([prev.signal_id,s.signal_id]))
        by_subject[key]=s; seen[s.signal_id]=s; unique.append(s)
    body=[s.to_dict() for s in unique]
    digest=_sha(_stable_json(body).encode())
    return SignalBatch("gisb-"+hashlib.sha256(digest.encode()).hexdigest()[:24], digest, tuple(unique), tuple(sorted(set(dup))), tuple(sorted(set(contradictions))), tuple(sorted(set(invalid))), counts)


def route_batch(batch: SignalBatch) -> tuple[RoutingReceipt, ...]:
    receipts=[]
    for s in batch.signals:
        reasons=list(s.reason_codes)
        disposition="diagnostic_only"; target=s.subject_path or s.spec_id or s.capability_id
        review="operator_review_required"
        prop=False
        if not s.routing_eligible or reasons or s.signal_id in batch.contradiction_ids:
            disposition="blocked_invalid"; reasons.append("invalid_or_contradicted"); review="manual_triage_required"
        elif s.finding_kind in GENESIS_KINDS and (s.capability_id or s.telemetry_stream):
            disposition="genesis_proposal_candidate"; target=s.capability_id or s.telemetry_stream; prop=True; reasons.append("missing_capability_or_new_flow")
        elif s.finding_kind in SPEC_KINDS and s.spec_id:
            disposition="spec_amendment_candidate"; target=s.spec_id; prop=True; reasons.append("existing_spec_recurring_failure")
        elif s.finding_kind in DIAGNOSTIC_KINDS:
            disposition="gap_seeker_diagnostic"; reasons.append("gap_seeker_supported_diagnostic")
        else:
            disposition="blocked_invalid"; reasons.append("no_safe_route")
        receipts.append(RoutingReceipt(s.signal_id, s.source_digest or batch.batch_digest, disposition, target, tuple(sorted(set(reasons))), review, prop, False, False, False, False))
    return tuple(sorted(receipts, key=lambda r: r.signal_id))


def evaluate_signal_plane(records: Iterable[Mapping[str, Any]] | Iterable[ImprovementSignal] = (), *, repo_root: Path | str = Path.cwd()) -> SignalPlaneEvaluation:
    batch=build_batch(records, repo_root=repo_root); receipts=route_batch(batch)
    counts: dict[str,int]={}
    for r in receipts: counts[r.disposition]=counts.get(r.disposition,0)+1
    genesis=[]; amendments=[]
    lookup={s.signal_id:s for s in batch.signals}
    for r in receipts:
        s=lookup[r.signal_id]
        if r.disposition=="genesis_proposal_candidate": genesis.append(s)
        if r.disposition=="spec_amendment_candidate": amendments.append({"spec_id":s.spec_id,"signal_type":s.finding_kind,"metadata":s.to_dict()})
    summary={"batch_id":batch.batch_id,"batch_digest":batch.batch_digest,"input_counts_by_source":dict(batch.input_counts_by_source or {}),"routed_counts_by_disposition":counts,"proposal_count":sum(1 for r in receipts if r.proposal_generation_occurred),"blocked_invalid_count":counts.get("blocked_invalid",0),"degraded": bool(batch.invalid_reasons or batch.contradiction_ids),"adoption_performed":False,"repository_mutation_performed":False,"provider_network_git_operation_performed":False}
    genesis_inputs={"telemetry_streams":[{"name":s.telemetry_stream or s.capability_id or s.signal_id,"capability":s.capability_id or s.telemetry_stream or s.signal_id,"description":s.description,"sample_payload":{"signal_id":s.signal_id,"batch_id":batch.batch_id}} for s in genesis],"vows":[{"capability":s.capability_id or s.telemetry_stream or s.signal_id,"description":"proposal-only review required"} for s in genesis]}
    return SignalPlaneEvaluation(batch, receipts, summary, genesis_inputs, tuple(amendments))


def atomic_write_json(path: Path | str, payload: Mapping[str, Any]) -> None:
    p=Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    data=json.dumps(payload, sort_keys=True, indent=2).encode()+b"\n"
    fd,tmp=tempfile.mkstemp(prefix=p.name+".", dir=str(p.parent))
    with os.fdopen(fd,"wb") as f: f.write(data)
    os.replace(tmp,p)


def render_markdown(e: SignalPlaneEvaluation) -> str:
    lines=["# Governed Improvement Signal Plane", "", f"- Batch: `{e.batch.batch_id}`", f"- Digest: `{e.batch.batch_digest}`", "- Adoption performed: `false`", "- Repository mutation performed: `false`", "", "## Routing"]
    for r in e.receipts: lines.append(f"- `{r.signal_id}` → `{r.disposition}` ({', '.join(r.reason_codes)})")
    return "\n".join(lines)+"\n"


def validate_evaluation(payload: Mapping[str, Any]) -> tuple[bool, tuple[str,...]]:
    reasons=[]
    if payload.get("schema") != "governed_improvement_signal_plane_evaluation:v1": reasons.append("wrong_schema")
    text=_stable_json(payload)
    for token in ("adoption_occurred\":true","repository_mutation_occurred\":true","provider_network_git_operation_occurred\":true"):
        if token in text: reasons.append("authority_claim_present")
    return (not reasons, tuple(sorted(set(reasons))))
