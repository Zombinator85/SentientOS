"""Side-effect-free canonical live-memory storage and explicit retention authority."""
from __future__ import annotations
import hashlib, json, os, re, tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from .windows_handle_custody import WindowsHandleCustodyError, read_explicit_file
CANDIDATE_TYPE = "explicit_conversation_user_retention"
MAX_RETENTION_RECORD_BYTES = 256 * 1024
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
    def verify_committed_artifact(self, receipt: Mapping[str, Any],
                                  source_turn: Mapping[str, Any],
                                  session_id: str) -> dict[str, Any]:
        """Verify the exact stored fragment without replaying admission or writes.

        This verifies artifact/source custody only. The original admission gate
        receipt is a digest in the transcript and is not durably reissued here.
        """
        if (not isinstance(session_id, str) or not session_id
                or source_turn.get("role") != "user"
                or not isinstance(source_turn.get("turn_id"), str)
                or not isinstance(source_turn.get("text"), str)
                or not isinstance(source_turn.get("text_digest"), str)
                or digest({"text": source_turn.get("text")}) != source_turn.get("text_digest")):
            return {"artifact_status": "unverified", "reason_code": "source_turn_invalid",
                    "admission_status": "not_independently_recoverable", "write_replayed": False}
        operation = "retain:" + session_id + ":" + source_turn["turn_id"]
        expected_id = "memory-" + hashlib.sha256(operation.encode()).hexdigest()[:24]
        expected_fields = {"status", "memory_id", "source_session_id", "source_turn_id",
            "source_text_digest", "admission_receipt_digest", "execution_operation_id",
            "canonical_stored_record_digest", "target_root_identity", "index_update_result"}
        receipt_digest = receipt.get("admission_receipt_digest")
        if (not isinstance(receipt, Mapping) or set(receipt) != expected_fields
                or receipt.get("status") != "memory_retention_committed"
                or receipt.get("memory_id") != expected_id
                or receipt.get("source_session_id") != session_id
                or receipt.get("source_turn_id") != source_turn["turn_id"]
                or receipt.get("source_text_digest") != source_turn["text_digest"]
                or receipt.get("execution_operation_id") != operation
                or receipt.get("target_root_identity") != digest({"root": str(self.store.root)})
                or receipt.get("index_update_result") != "raw_fragment_available"
                or not isinstance(receipt_digest, str)
                or len(receipt_digest) != 64
                or any(char not in "0123456789abcdef" for char in receipt_digest)):
            return {"artifact_status": "conflict", "reason_code": "stored_receipt_binding_invalid",
                    "admission_status": "not_independently_recoverable", "write_replayed": False}
        stored_digest = receipt.get("canonical_stored_record_digest")
        if (not isinstance(stored_digest, str) or len(stored_digest) != 64
                or any(char not in "0123456789abcdef" for char in stored_digest)):
            return {"artifact_status": "conflict", "reason_code": "stored_record_digest_invalid",
                    "admission_status": "not_independently_recoverable", "write_replayed": False}
        path = self.store.raw / (expected_id + ".json")
        try:
            raw = read_explicit_file(path, max_bytes=MAX_RETENTION_RECORD_BYTES)
        except WindowsHandleCustodyError as exc:
            reason = ("artifact_missing" if exc.args == ("explicit_file_missing",)
                      else "artifact_custody_unavailable")
            return {"artifact_status": "unavailable", "reason_code": reason,
                    "admission_status": "not_independently_recoverable", "write_replayed": False}
        try:
            record = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            return {"artifact_status": "conflict", "reason_code": "artifact_malformed",
                    "admission_status": "not_independently_recoverable", "write_replayed": False}
        fields = {"id", "text", "text_digest", "timestamp", "source", "category",
                  "tags", "importance", "meta"}
        meta = record.get("meta") if isinstance(record, dict) else None
        expected_meta_fields = {"session_id", "turn_id", "request_id", "operation_id",
                                "admission_receipt_digest"}
        timestamp = record.get("timestamp") if isinstance(record, dict) else None
        try:
            instant = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
            timestamp_valid = instant.tzinfo is not None and instant.utcoffset() is not None
        except (OverflowError, OSError, TypeError, ValueError):
            timestamp_valid = False
        if (not isinstance(record, dict) or set(record) != fields
                or record.get("id") != expected_id
                or record.get("text") != source_turn["text"]
                or record.get("text_digest") != source_turn["text_digest"]
                or record.get("source") != "conversation_user_turn"
                or record.get("category") != "event"
                or record.get("tags") != ["explicit-retention"]
                or type(record.get("importance")) is not float
                or record.get("importance") != 1.0
                or not isinstance(meta, dict) or set(meta) != expected_meta_fields
                or meta.get("session_id") != session_id
                or meta.get("turn_id") != source_turn["turn_id"]
                or not isinstance(meta.get("request_id"), str)
                or not re.fullmatch(r"retain-request-[0-9a-f]{24}", meta.get("request_id", ""))
                or meta.get("operation_id") != operation
                or meta.get("admission_receipt_digest") != receipt_digest
                or not timestamp_valid or digest(record) != stored_digest):
            return {"artifact_status": "conflict", "reason_code": "stored_artifact_binding_invalid",
                    "admission_status": "not_independently_recoverable", "write_replayed": False}
        return {"artifact_status": "verified", "memory_id": expected_id,
                "record_digest": stored_digest,
                "admission_status": "not_independently_recoverable",
                "reason_code": "admission_receipt_not_durably_custodied",
                "write_replayed": False}
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
