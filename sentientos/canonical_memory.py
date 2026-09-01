"""Side-effect-free canonical live-memory storage and explicit retention authority."""
from __future__ import annotations
import hashlib, json, os, re, tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
CANDIDATE_TYPE = "explicit_conversation_user_retention"
def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
def sentientos_data_dir() -> Path:
    return Path(os.getenv("SENTIENTOS_DATA_DIR") or os.getenv("SENTIENTOS_DATA_ROOT") or (Path.cwd()/"sentientos_data")).expanduser().resolve()
@dataclass(frozen=True)
class RetentionAdmission:
    decision: str; candidate_digest: str; request_id: str; receipt_digest: str; reason: str|None=None
class ExplicitRetentionAdmissionGate:
    """Independent, default-deny authority for an exact structured user request."""
    def decide(self, candidate: Mapping[str, Any]) -> RetentionAdmission:
        required=("session_id","source_turn_id","source_text_digest","request_id","operation_id")
        valid=(candidate.get("candidate_type")==CANDIDATE_TYPE and candidate.get("explicitly_requested") is True
               and candidate.get("source_role")=="user" and all(candidate.get(k) for k in required))
        cd=digest(candidate); decision="retention_admitted" if valid else "retention_denied"
        body={"decision":decision,"candidate_digest":cd,"request_id":str(candidate.get("request_id") or ""),"authority":"explicit_retention_admission_gate"}
        return RetentionAdmission(decision,cd,body["request_id"],digest(body),None if valid else "invalid_explicit_user_candidate")
class CanonicalMemoryStore:
    """Canonical raw-fragment domain compatible with memory_manager.RAW_PATH."""
    def __init__(self,memory_root:Path)->None:
        self.root=memory_root.resolve(); self.raw=self.root/"raw"; self.raw.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.legacy_sidecar_present=(self.root/"conversation_memories.json").is_file()
    def _records(self)->list[dict[str,Any]]:
        out=[]
        for path in sorted(self.raw.glob("*.json")):
            try:
                value=json.loads(path.read_text(encoding="utf-8"))
                if isinstance(value,dict) and isinstance(value.get("text"),str): out.append(value)
            except (OSError,json.JSONDecodeError): pass
        return out
    def retrieve(self,query:str,*,limit:int=4,budget_chars:int=2000)->dict[str,Any]:
        terms=set(re.findall(r"[a-z0-9]+",query.lower())); ranked=[]
        for record in self._records():
            score=len(terms & set(re.findall(r"[a-z0-9]+",record["text"].lower())))
            if score: ranked.append((score,str(record.get("id","")),record))
        selected: list[dict[str, Any]]=[]; used=0
        for _,_,record in sorted(ranked,key=lambda x:(-x[0],x[1])):
            if len(selected)>=max(0,limit): break
            if used+len(record["text"])<=budget_chars: selected.append(record); used+=len(record["text"])
        identities=[(r.get("id"),r.get("text_digest") or digest({"text":r["text"]})) for r in selected]
        return {"memories":selected,"selected_memory_ids":[x[0] for x in identities],"read_only":True,"legacy_sidecar_present":self.legacy_sidecar_present,
                "snapshot_digest":digest({"query_digest":digest({"query":query}),"selected":identities,"limit":limit,"budget_chars":budget_chars})}
class AdmittedRetentionWriter:
    """Terminal executor validates admission evidence but never decides admission."""
    def __init__(self,store:CanonicalMemoryStore)->None:self.store=store
    def execute(self,candidate:Mapping[str,Any],admission:RetentionAdmission,source_turn:Mapping[str,Any])->dict[str,Any]:
        if admission.decision!="retention_admitted" or admission.candidate_digest!=digest(candidate): raise PermissionError("valid_admission_evidence_required")
        if candidate.get("candidate_type")!=CANDIDATE_TYPE or candidate.get("source_role")!="user": raise PermissionError("invalid_retention_candidate")
        if source_turn.get("role")!="user" or source_turn.get("turn_id")!=candidate.get("source_turn_id"): raise PermissionError("source_turn_mismatch")
        if source_turn.get("text_digest")!=candidate.get("source_text_digest") or digest({"text":source_turn.get("text")})!=candidate.get("source_text_digest"): raise PermissionError("source_text_mismatch")
        op=str(candidate["operation_id"]); mid="memory-"+hashlib.sha256(op.encode()).hexdigest()[:24]; path=self.store.raw/f"{mid}.json"
        record={"id":mid,"text":source_turn["text"],"text_digest":source_turn["text_digest"],"timestamp":datetime.now(timezone.utc).isoformat(),"source":"conversation_user_turn","category":"event","tags":["explicit-retention"],"importance":1.0,
                "meta":{"session_id":candidate["session_id"],"turn_id":candidate["source_turn_id"],"request_id":candidate["request_id"],"operation_id":op,"admission_receipt_digest":admission.receipt_digest}}
        if path.exists():
            existing=json.loads(path.read_text(encoding="utf-8"))
            for key in ("text","text_digest","source","meta"):
                if existing.get(key)!=record.get(key): raise PermissionError("operation_replay_mismatch")
            record=existing
        else:
            fd,temp=tempfile.mkstemp(prefix=".memory-",dir=self.store.raw)
            with os.fdopen(fd,"w",encoding="utf-8") as stream: json.dump(record,stream,sort_keys=True,ensure_ascii=False);stream.write("\n");stream.flush();os.fsync(stream.fileno())
            os.replace(temp,path)
        return {"status":"memory_retention_committed","memory_id":mid,"source_session_id":candidate["session_id"],"source_turn_id":candidate["source_turn_id"],"source_text_digest":candidate["source_text_digest"],"admission_receipt_digest":admission.receipt_digest,"execution_operation_id":op,"canonical_stored_record_digest":digest(record),"target_root_identity":digest({"root":str(self.store.root)}),"index_update_result":"raw_fragment_available"}
