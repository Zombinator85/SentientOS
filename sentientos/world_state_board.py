# mypy: disable-error-code="no-untyped-def,no-untyped-call,var-annotated,dict-item"
"""Deterministic read-only world-state evidence board.

This module projects bounded, typed local evidence into a view-only snapshot. It
never admits, executes, adopts, mutates repositories, invokes models, calls Git,
or performs host effects.
"""
from __future__ import annotations

import hashlib, json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

SCHEMA_VERSION="world_state_board.v1"
LIFECYCLE_STAGES=("observation","proposal","review","admission","execution","rollback","adoption","repository_handoff","repository_landing")
FALSE_AUTHORITY={"decision_authority":False,"admission_authority":False,"execution_authority":False,"adoption_authority":False,"repository_mutation_authority":False}

class WorldStateSourceKind(str, Enum):
    CAPABILITY_REGISTRY="capability_registry"; CONTROL_PLANE_DECISION="control_plane_decision"; RUNTIME_SUPERVISOR="runtime_supervisor"; IMPROVEMENT_SIGNAL="governed_improvement_signal_plane"; LOCAL_MODEL_AUTHORITY="local_model_authority"; GENESIS_ADVICE="genesis_advice"; GENESIS_CANDIDATE="genesis_candidate"; SPEC_AMENDMENT="specification_amendment"; REPOSITORY_MUTATION_HANDOFF="repository_mutation_handoff"; AUDIT_TRUST="audit_trust"; QUARANTINE="quarantine"; PANIC="panic"; HOST_INVENTORY="host_inventory"; RESOURCE_GOVERNOR="resource_governor"; PRIVILEGE="privilege"; EMBODIMENT="embodiment"; FULFILLMENT="fulfillment"

@dataclass(frozen=True)
class WorldStateSubject: subject_id:str; subject_kind:str; labels:tuple[str,...]=()
@dataclass(frozen=True)
class WorldStateSourceRef: source_id:str; kind:str; schema_version:str; digest:str; required:bool=False; path_hint:str|None=None; staleness:str="not_applicable"; finding:str="ok"
@dataclass(frozen=True)
class WorldStateFact:
    fact_id:str; subject:WorldStateSubject; stage:str; disposition:str; evidence_strength:str; source:WorldStateSourceRef; payload:Mapping[str,Any]=field(default_factory=dict); effect_claimed:bool=False; effect_proven:bool=False; observed_at:str|None=None
@dataclass(frozen=True)
class WorldStateLineageEdge: edge_id:str; from_id:str; to_id:str; relation:str; source_id:str
@dataclass(frozen=True)
class WorldStateConflict: conflict_id:str; conflict_type:str; subject_id:str; fact_ids:tuple[str,...]; severity:str="warning"; description:str=""
@dataclass(frozen=True)
class WorldStateStagePosture: stage:str; disposition:str="unknown"; evidence_strength:str="unknown"; staleness:str="undated"; contradicted:bool=False; fact_ids:tuple[str,...]=()
@dataclass(frozen=True)
class WorldStateEntity: subject:WorldStateSubject; stage_postures:tuple[WorldStateStagePosture,...]; fact_ids:tuple[str,...]
@dataclass(frozen=True)
class WorldStateBoardSummary: counts:Mapping[str,Mapping[str,int]]; warnings:int=0; risks:int=0; conflicts:int=0; pending_review:int=0; denied:int=0; deferred:int=0; blocked:int=0; degraded:int=0; contradicted:int=0; execution_attempts:int=0; proven_completions:int=0; rollbacks:int=0; adoptions:int=0; repository_handoffs:int=0; repository_landings:int=0; unproven_effect_claims:int=0
@dataclass(frozen=True)
class WorldStateSourceManifest: manifest_id:str; digest:str; allowed_roots:tuple[str,...]; sources:tuple[WorldStateSourceRef,...]; max_source_count:int=64; max_artifact_size:int=1048576
@dataclass(frozen=True)
class WorldStateSnapshot:
    snapshot_id:str; digest:str; manifest:WorldStateSourceManifest; sources:tuple[WorldStateSourceRef,...]; facts:tuple[WorldStateFact,...]; conflicts:tuple[WorldStateConflict,...]; lineage:tuple[WorldStateLineageEdge,...]; entities:tuple[WorldStateEntity,...]; summary:WorldStateBoardSummary; custody:Mapping[str,Any]; degraded:bool; stale:bool; contradicted:bool; validation_posture:str; authority:Mapping[str,bool]=field(default_factory=lambda: FALSE_AUTHORITY)
@dataclass(frozen=True)
class WorldStateDelta: delta_id:str; digest:str; changes:tuple[Mapping[str,Any],...]
@dataclass(frozen=True)
class WorldStateValidationResult: valid:bool; findings:tuple[str,...]

def _canon(o:Any)->str: return json.dumps(o, sort_keys=True, separators=(",",":"), default=lambda x: asdict(x) if hasattr(x,"__dataclass_fields__") else str(x))
def digest(o:Any)->str: return hashlib.sha256(_canon(o).encode()).hexdigest()
def _sid(prefix:str, payload:Any)->str: return f"{prefix}-{digest(payload)[:16]}"
def to_dict(o:Any)->Any: return json.loads(_canon(o))
def _parse_time(s:str|None):
    if not s: return None
    try: return datetime.fromisoformat(s.replace("Z","+00:00"))
    except ValueError: return None

def staleness_for(kind:str, observed_at:str|None, now:datetime)->str:
    historical={"specification_amendment","repository_mutation_handoff","genesis_candidate"}
    if kind in historical: return "not_applicable"
    t=_parse_time(observed_at)
    if t is None: return "undated"
    age=(now-t).total_seconds()
    if age < 3600: return "fresh"
    if age < 86400: return "aging"
    if age < 7*86400: return "stale"
    return "expired"

class WorldStateBoardBuilder:
    def __init__(self, *, allowed_roots:Sequence[Path|str]=(), max_source_count:int=64, max_artifact_size:int=1048576, clock:Callable[[],datetime]|None=None):
        self.allowed_roots=tuple(str(Path(r).resolve()) for r in allowed_roots); self.max_source_count=max_source_count; self.max_artifact_size=max_artifact_size; self.clock=clock or (lambda: datetime.now(timezone.utc))
    def build(self, records:Sequence[Mapping[str,Any]]=(), *, manifest_id:str="world-state-manifest") -> WorldStateSnapshot:
        now=self.clock(); sources=[]; facts=[]; conflicts=[]; lineage=[]; seen={}
        if len(records)>self.max_source_count: records=records[:self.max_source_count]; conflicts.append(WorldStateConflict("conflict-source-count","manifest_bounds","manifest",(),"error","maximum source count exceeded"))
        for i,r in enumerate(records):
            kind=str(r.get("source_kind", r.get("kind","capability_registry")))
            if kind not in {k.value for k in WorldStateSourceKind}: raise ValueError(f"unsupported source kind: {kind}")
            sid=str(r.get("source_id") or f"{kind}:{i}"); content={k:v for k,v in r.items() if k not in {"observed_at","retrieved_at","latency","absolute_path","temporary_root","process_id","dashboard_request_time","output_location"}}
            dg=str(r.get("digest") or digest(content)); finding="ok"
            if r.get("digest") and r.get("digest") != digest(content): finding="digest-mismatch"
            st=staleness_for(kind, r.get("observed_at"), now)
            src=WorldStateSourceRef(sid,kind,str(r.get("schema_version","v1")),dg,bool(r.get("required",False)), "redacted", st, finding)
            sources.append(src)
            if sid in seen and seen[sid]!=dg: conflicts.append(WorldStateConflict(_sid("conflict",(sid,seen[sid],dg)),"source_digest_mismatch",sid,(),"error","one semantic source id has different digests"))
            seen[sid]=dg
            subj=WorldStateSubject(str(r.get("subject_id",sid)), str(r.get("subject_kind",kind)))
            stage=str(r.get("stage","observation"));
            if stage not in LIFECYCLE_STAGES: raise ValueError(f"unsupported lifecycle stage: {stage}")
            disp=str(r.get("disposition","unknown")); eff=bool(r.get("effect_claimed",False)); proven=bool(r.get("effect_proven",False))
            payload=dict(r.get("payload",{}))
            fid=_sid("fact",(subj.subject_id,subj.subject_kind,stage,disp,src.digest,payload,eff,proven))
            facts.append(WorldStateFact(fid,subj,stage,disp,str(r.get("evidence_strength","recorded")),src,payload,eff,proven,r.get("observed_at")))
        conflicts += self._detect_conflicts(facts)
        entities=self._entities(facts,conflicts)
        counts=self._counts(sources,facts)
        summary=WorldStateBoardSummary(counts=counts, conflicts=len(conflicts), pending_review=sum(f.disposition in {"pending","ready_for_review"} for f in facts), denied=sum(f.disposition=="deny" for f in facts), deferred=sum(f.disposition=="deferred" for f in facts), blocked=sum(f.disposition=="blocked" for f in facts), degraded=sum(s.finding!="ok" for s in sources), contradicted=len(conflicts), execution_attempts=sum(f.stage=="execution" for f in facts), proven_completions=sum(f.stage=="execution" and f.effect_proven for f in facts), rollbacks=sum(f.stage=="rollback" for f in facts), adoptions=sum(f.stage=="adoption" for f in facts), repository_handoffs=sum(f.stage=="repository_handoff" for f in facts), repository_landings=sum(f.stage=="repository_landing" for f in facts), unproven_effect_claims=sum(f.effect_claimed and not f.effect_proven for f in facts))
        man=WorldStateSourceManifest(manifest_id,digest((self.allowed_roots, [to_dict(s) for s in sources])),self.allowed_roots,tuple(sorted(sources,key=lambda s:s.source_id)),self.max_source_count,self.max_artifact_size)
        base={"schema_version":SCHEMA_VERSION,"manifest_digest":man.digest,"sources":[to_dict(s) for s in man.sources],"facts":[to_dict(f) for f in sorted(facts,key=lambda f:f.fact_id)],"conflicts":[to_dict(c) for c in sorted(conflicts,key=lambda c:c.conflict_id)],"summary":to_dict(summary),"authority":FALSE_AUTHORITY}
        dg=digest(base); snap=WorldStateSnapshot(f"world-state-{dg[:16]}",dg,man,man.sources,tuple(sorted(facts,key=lambda f:f.fact_id)),tuple(sorted(conflicts,key=lambda c:c.conflict_id)),tuple(lineage),entities,summary,{"observed_at":now.isoformat(),"schema_version":SCHEMA_VERSION},summary.degraded>0, any(s.staleness in {"stale","expired","undated"} for s in sources), bool(conflicts), "valid", FALSE_AUTHORITY)
        return snap
    def _counts(self,sources,facts):
        out={k:{} for k in ["subject_kind","source_kind","lifecycle_stage","disposition","evidence_strength","staleness_posture"]}
        def inc(cat,k): out[cat].__setitem__(str(k), out[cat].get(str(k),0)+1)
        for s in sources: inc("source_kind",s.kind); inc("staleness_posture",s.staleness)
        for f in facts: inc("subject_kind",f.subject.subject_kind); inc("lifecycle_stage",f.stage); inc("disposition",f.disposition); inc("evidence_strength",f.evidence_strength)
        return out
    def _detect_conflicts(self,facts):
        conflicts=[]; groups={}
        for f in facts: groups.setdefault((f.subject.subject_id,f.stage),[]).append(f)
        pairs=[({"allow","deny"},"allow_deny"),({"completed","failed"},"completed_failed"),({"adopted","rejected"},"adopted_rejected"),({"eligible","blocked"},"eligible_blocked"),({"nominal","contradicted"},"nominal_contradicted")]
        for (sid,stage),fs in groups.items():
            ds={f.disposition for f in fs}
            for vals,typ in pairs:
                if vals<=ds: conflicts.append(WorldStateConflict(_sid("conflict",(sid,stage,typ,sorted(x.fact_id for x in fs))),typ,sid,tuple(sorted(f.fact_id for f in fs)),"error",typ))
            if any(f.effect_claimed and not f.effect_proven and f.payload.get("false_effect_receipt") for f in fs): conflicts.append(WorldStateConflict(_sid("conflict",(sid,stage,"false_effect")),"false_effect_receipt",sid,tuple(sorted(f.fact_id for f in fs)),"error","effect claim paired with false-effect receipt"))
        return conflicts
    def _entities(self,facts,conflicts):
        by={}; contrad={c.subject_id for c in conflicts}
        for f in facts: by.setdefault(f.subject.subject_id,[]).append(f)
        ents=[]
        for sid,fs in sorted(by.items()):
            posts=[]
            for st in LIFECYCLE_STAGES:
                sfs=[f for f in fs if f.stage==st]
                posts.append(WorldStateStagePosture(st, sfs[-1].disposition if sfs else "unknown", sfs[-1].evidence_strength if sfs else "unknown", sfs[-1].source.staleness if sfs else "undated", sid in contrad, tuple(sorted(f.fact_id for f in sfs))))
            ents.append(WorldStateEntity(fs[0].subject,tuple(posts),tuple(sorted(f.fact_id for f in fs))))
        return tuple(ents)

def validate_snapshot(snapshot:WorldStateSnapshot)->WorldStateValidationResult:
    expected=digest({"schema_version":SCHEMA_VERSION,"manifest_digest":snapshot.manifest.digest,"sources":[to_dict(s) for s in snapshot.sources],"facts":[to_dict(f) for f in snapshot.facts],"conflicts":[to_dict(c) for c in snapshot.conflicts],"summary":to_dict(snapshot.summary),"authority":snapshot.authority})
    findings=[]
    if expected!=snapshot.digest: findings.append("snapshot_digest_mismatch")
    if any(snapshot.authority.values()): findings.append("authority_field_true")
    return WorldStateValidationResult(not findings,tuple(findings))

def diff_snapshots(before:WorldStateSnapshot, after:WorldStateSnapshot)->WorldStateDelta:
    bf={f.fact_id:f for f in before.facts}; af={f.fact_id:f for f in after.facts}; changes=[]
    for fid in sorted(set(af)-set(bf)): changes.append({"change":"new_observation","fact_id":fid})
    for fid in sorted(set(bf)-set(af)): changes.append({"change":"disappearance_from_current_observation","fact_id":fid,"deletion_claimed":False})
    for c in after.conflicts:
        if c.conflict_id not in {x.conflict_id for x in before.conflicts}: changes.append({"change":"new_conflict","conflict_id":c.conflict_id})
    did=digest(changes); return WorldStateDelta(f"world-state-delta-{did[:16]}",did,tuple(changes))
