"""Bounded bridge from canonical maintenance closure to continuity derivation.

This controller only discovers and normalizes existing custody.  It neither does
maintenance nor adopts wake ownership or resident Python code.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, cast

from sentientos import maintenance_authority_continuity as continuity
from sentientos import maintenance_commit_publication as publication
from sentientos import maintenance_loop_watchdog as watchdog
from sentientos import maintenance_successor_generation_adoption as adoption
from sentientos import maintenance_task_authority_lease as leases
from sentientos import maintenance_task_journal as journal
from sentientos import maintenance_validation_controller as validation
from sentientos import maintenance_wake_cycle as wake
from sentientos import maintenance_autonomy_cycle as autonomy

CONFIG_SCHEMA = "sentientos.maintenance_authority_continuity_auto_derivation_config:v1"
EVENT_SCHEMA = "sentientos.maintenance_authority_continuity_auto_derivation_event:v1"
RECEIPT_SCHEMA = "sentientos.maintenance_authority_continuity_auto_derivation_receipt:v1"
RESULT_SCHEMA = "sentientos.maintenance_authority_continuity_auto_derivation_result:v1"
ZERO_DIGEST = "sha256:" + "0" * 64
PHASES = ("transition_intent_recorded", "canonical_evidence_normalized",
          "continuity_derivation_intended", "auto_derivation_completed")

def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()

def digest(value: Mapping[str, Any], omitted: str | None = None) -> str:
    body = {k: v for k, v in value.items() if k != omitted} if omitted else dict(value)
    return "sha256:" + hashlib.sha256(canonical_bytes(body)).hexdigest()

def _load(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if p.is_symlink() or not p.is_file(): raise ValueError("auto_derivation_input_not_regular")
    value = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(value, dict): raise ValueError("auto_derivation_input_not_object")
    return cast(dict[str, Any], value)

def _private(path: Path) -> None:
    if path.exists():
        if path.is_symlink() or not path.is_dir() or (os.name == "posix" and stat.S_IMODE(os.lstat(path).st_mode) != 0o700):
            raise ValueError("auto_derivation_custody_unsafe")
    else: path.mkdir(parents=True, mode=0o700)

def _write(path: Path, value: Mapping[str, Any]) -> str:
    data = canonical_bytes(value) + b"\n"; _private(path.parent)
    if path.exists():
        if path.is_symlink() or path.read_bytes() != data: raise ValueError("auto_derivation_output_conflict")
        return "reused"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as out: out.write(data); out.flush(); os.fsync(out.fileno())
    return "created"

def validate_config(value: Mapping[str, Any]) -> dict[str, Any]:
    keys = {"schema_version", "enabled", "continuity_policy_path", "continuity_policy_digest",
            "successor_adoption_config_path", "successor_adoption_config_digest", "repository_identity",
            "repository_root", "state_root", "evidence_root", "journal_path", "stop_marker",
            "observation_interval_seconds", "maximum_successful_derivations", "maximum_wall_clock_seconds",
            "shutdown_timeout_seconds", "config_digest"}
    result = dict(value)
    if set(result) != keys or result.get("schema_version") != CONFIG_SCHEMA or type(result.get("enabled")) is not bool:
        raise ValueError("invalid_auto_derivation_config")
    expected = digest(result, "config_digest")
    if result.get("config_digest") not in ("", expected): raise ValueError("auto_derivation_config_digest_mismatch")
    result["config_digest"] = expected
    for key in ("maximum_successful_derivations", "maximum_wall_clock_seconds"):
        if type(result[key]) is not int or result[key] < 1: raise ValueError("invalid_auto_derivation_bound")
    for key in ("observation_interval_seconds", "shutdown_timeout_seconds"):
        if type(result[key]) not in (int, float) or result[key] <= 0: raise ValueError("invalid_auto_derivation_bound")
    if not result["enabled"]: return result
    repo = Path(result["repository_root"]).resolve(strict=True)
    for key in ("state_root", "evidence_root"):
        external = Path(result[key]).resolve(strict=True)
        if external == repo or repo in external.parents: raise ValueError("auto_derivation_custody_inside_repository")
    policy = continuity.validate_policy(_load(result["continuity_policy_path"]))
    successor = adoption.validate_config(_load(result["successor_adoption_config_path"]))
    if policy["policy_digest"] != result["continuity_policy_digest"]: raise ValueError("continuity_policy_digest_mismatch")
    if successor["config_digest"] != result["successor_adoption_config_digest"]: raise ValueError("successor_adoption_config_digest_mismatch")
    if not successor["enabled"] or Path(successor["continuity_policy_path"]).resolve() != Path(result["continuity_policy_path"]).resolve() or successor["continuity_policy_digest"] != policy["policy_digest"]:
        raise ValueError("bound_successor_adoption_posture_invalid")
    if successor["repository_identity"] != result["repository_identity"] or Path(successor["repository_root"]).resolve() != repo:
        raise ValueError("repository_binding_mismatch")
    result["repository_root"] = str(repo)
    return result

def load_config(path: str | Path) -> dict[str, Any]: return validate_config(_load(path))

def _events(cfg: Mapping[str, Any]) -> list[dict[str, Any]]:
    path = Path(cfg["journal_path"]); rows: list[dict[str, Any]] = []; prior = ZERO_DIGEST
    if not path.exists(): return rows
    if path.is_symlink(): raise ValueError("auto_derivation_journal_corrupt")
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line); claimed = row.pop("event_digest")
            if row.get("schema_version") != EVENT_SCHEMA or row.get("config_digest") != cfg["config_digest"] or row.get("prior_event_digest") != prior or digest(row) != claimed: raise ValueError
            row["event_digest"] = claimed; rows.append(row); prior = claimed
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc: raise ValueError("auto_derivation_journal_corrupt") from exc
    for i, row in enumerate(rows):
        if row.get("event_type") != PHASES[i % 4]: raise ValueError("auto_derivation_recovery_ambiguous")
        first = rows[i - i % 4]
        if any(row.get(k) != first.get(k) for k in ("lineage_id", "adopted_ordinal", "adopted_generation_digest", "task_id", "closure_event_digest", "evaluation_time")):
            raise ValueError("auto_derivation_journal_branched")
        # A later phase may add bindings, but it may never contradict a binding
        # already made by an earlier phase of the same transaction.
        for earlier in rows[i - i % 4:i]:
            for key in ("completion_adapter_digest", "successor_adapter_digest",
                        "continuity_generation_digest", "auto_receipt_path",
                        "auto_receipt_digest"):
                if key in earlier and key in row and earlier[key] != row[key]:
                    raise ValueError("auto_derivation_journal_branched")
    return rows

def _append(cfg: Mapping[str, Any], event_type: str, identity: Mapping[str, Any], **extra: Any) -> dict[str, Any]:
    rows = _events(cfg); row = {"schema_version": EVENT_SCHEMA, "config_digest": cfg["config_digest"],
        "event_type": event_type, **identity, "prior_event_digest": rows[-1]["event_digest"] if rows else ZERO_DIGEST, **extra}
    row["event_digest"] = digest(row); path = Path(cfg["journal_path"]); _private(path.parent)
    fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "ab") as out: out.write(canonical_bytes(row) + b"\n"); out.flush(); os.fsync(out.fileno())
    return row

def _only(root: Path, directory: str, schema: str, task: str, link: tuple[str, str] | None = None) -> tuple[Path, dict[str, Any]]:
    matches = []
    folder = root / directory
    for path in sorted(folder.glob("*.json"), key=lambda p: p.name) if folder.is_dir() else ():
        try: value = _load(path)
        except (OSError, ValueError, json.JSONDecodeError): continue
        if value.get("schema_version") == schema and value.get("task_id") == task and (link is None or value.get(link[0]) == link[1]): matches.append((path.resolve(), value))
    if len(matches) != 1: raise ValueError("canonical_artifact_match_ambiguous" if matches else "canonical_artifact_missing")
    return matches[0]

def _require_native_digest(value: Mapping[str, Any], key: str) -> None:
    """Require the artifact's native closed-object digest during discovery."""
    if not isinstance(value.get(key), str) or value[key] != publication._seal({**value, key: ""}, key):
        raise ValueError("canonical_artifact_digest_invalid")

def _watchdog_from_adoption(wake_adoption: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    wc = wake.load_config(wake_adoption["wake_config_path"])
    ac = autonomy.load_config(wc["autonomy_cycle_configuration_path"])
    wd = watchdog.load_config(ac["watchdog_configuration_path"])
    return wc, wd

def _discover(cfg: Mapping[str, Any], generation: Mapping[str, Any], wake_adoption: Mapping[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]] | None:
    _, wd = _watchdog_from_adoption(wake_adoption); root = Path(wd["state_root"])
    snapshots = journal.discover_maintenance_task_snapshots(root, repo_root=cfg["repository_root"])
    if any(item.get("integrity_status") != "journal_ready" for item in snapshots): raise ValueError("canonical_task_journal_corrupt")
    candidates = []
    for item in snapshots:
        snap = item.get("snapshot", {})
        if snap.get("base_sha") != generation["base_sha"] or snap.get("lifecycle_state") != "closed" or snap.get("publication_state") != "succeeded": continue
        task = str(item["task_id"])
        try:
            lease_p, lease = _only(root, "maintenance_leases", leases.LEASE_SCHEMA, task)
            val_p, val = _only(root, "maintenance_validation_results", validation.RESULT_SCHEMA, task)
            plan_p, plan = _only(root, "maintenance_commit_plans", publication.COMMIT_PLAN_SCHEMA, task, ("validation_result_digest", val["result_digest"]))
            commit_p, commit = _only(root, "maintenance_commit_results", publication.COMMIT_RESULT_SCHEMA, task, ("plan_digest", plan["plan_digest"]))
            request_p, request = _only(root, "maintenance_publication_requests", publication.PUBLICATION_REQUEST_SCHEMA, task, ("commit_result_digest", commit["commit_result_digest"]))
            result_p, result = _only(root, "maintenance_publication_results", publication.PUBLICATION_RESULT_SCHEMA, task, ("request_digest", request["publication_request_digest"]))
            for value, key in ((lease,"lease_digest"),(val,"result_digest"),(plan,"plan_digest"),
                               (commit,"commit_result_digest"),(request,"publication_request_digest"),
                               (result,"publication_result_digest")):
                _require_native_digest(value, key)
            if lease.get("grant_generation") != generation["generation_digest"]:
                raise ValueError("terminal_success_lease_generation_mismatch")
            if lease.get("base_sha") != generation["base_sha"]:
                raise ValueError("terminal_success_lease_base_mismatch")
            if val.get("terminal_status") != "validation_ready_for_commit":
                raise ValueError("terminal_success_validation_not_ready")
            if plan.get("validation_result_digest") != val["result_digest"] or plan.get("base_sha") != generation["base_sha"]:
                raise ValueError("terminal_success_commit_validation_chain_mismatch")
            if (commit.get("validation_result_digest") != val["result_digest"] or
                    commit.get("parent_sha") != generation["base_sha"]):
                raise ValueError("terminal_success_commit_validation_chain_mismatch")
            if (request.get("commit_sha") != commit.get("commit_sha") or
                    request.get("parent_sha") != commit.get("parent_sha") or
                    request.get("validation_result_digest") != val["result_digest"]):
                raise ValueError("terminal_success_publication_request_chain_mismatch")
            if result.get("terminal_status") != "publication_succeeded":
                raise ValueError("terminal_success_publication_result_mismatch")
            if result.get("mode") != publication.LOCAL_FAST_FORWARD_MODE:
                raise ValueError("terminal_success_landing_mode_mismatch")
            if result.get("parent_sha") != generation["base_sha"]:
                raise ValueError("terminal_success_landing_parent_mismatch")
            if result.get("commit_sha") != commit.get("commit_sha"):
                raise ValueError("terminal_success_landing_commit_mismatch")
            sources = {"journal_path": str((root/"maintenance_tasks"/f"{task}.jsonl").resolve()), "lease_path":str(lease_p), "validation_result_path":str(val_p), "commit_plan_path":str(plan_p), "commit_result_path":str(commit_p), "publication_request_path":str(request_p), "landing_result_path":str(result_p)}
            candidates.append((task, snap, {"lease":lease,"validation":val,"plan":plan,"commit":commit,"request":request,"result":result,"paths":sources,"state_root":root}))
        except (KeyError, ValueError) as exc:
            # Once the journal claims terminal successful publication, its
            # authority-bearing custody is mandatory, not another waiting case.
            raise ValueError(f"canonical_successful_closure_custody_broken:{task}:{exc}") from exc
    if len(candidates) > 1: raise ValueError("ambiguous_completed_maintenance_transition")
    if candidates: return candidates[0]
    if any(i.get("snapshot", {}).get("base_sha") == generation["base_sha"] and i.get("snapshot", {}).get("publication_state") == "succeeded" for i in snapshots):
        raise RuntimeError("waiting_for_terminal_closure")
    return None

def derive_once(config: Mapping[str, Any], *, evaluation_time: str | None = None) -> dict[str, Any]:
    cfg = validate_config(config); effects: list[str] = []
    if not cfg["enabled"]: return {"schema_version":RESULT_SCHEMA,"status":"disabled","effect_count":0}
    bound = adoption.load_config(cfg["successor_adoption_config_path"]); adopted, wake_adoption = adoption.reconstruct_current(bound)
    policy = continuity.validate_policy(_load(cfg["continuity_policy_path"]))
    events = _events(cfg)
    tail = events[len(events)-len(events)%4:] if len(events)%4 else []
    # Pending recovery precedes strict current-generation reconstruction.  This
    # narrow seam lets derive_next inspect an exact half-written N+1 pair while
    # all ordinary continuity readers remain strict.
    current = continuity._current_generation(policy, allow_exact_partial=bool(tail))
    if Path(cfg["stop_marker"]).exists() or Path(bound["stop_marker"]).exists() or Path(wake_adoption["stop_marker"]).exists(): return {"schema_version":RESULT_SCHEMA,"status":"paused","effect_count":0}
    _, wd = _watchdog_from_adoption(wake_adoption)
    control = watchdog.inspect_control(wd)
    paused = Path(wd.get("stop_marker") or Path(wd["state_root"]) / "STOP").exists() or control.get("paused") or control.get("status") != "ready"
    if paused:
        # While paused, only seal custody whose continuity effect is already a
        # complete N+1.  No normalization or derive_next invocation is allowed.
        if not (tail and len(tail) == 3 and current["ordinal"] == adopted["ordinal"] + 1):
            return {"schema_version":RESULT_SCHEMA,"status":"paused","effect_count":0}
    delta = current["ordinal"] - adopted["ordinal"]
    if delta == 1 and not tail:
        return {"schema_version":RESULT_SCHEMA,"status":"waiting_for_successor_adoption","effect_count":0,"adopted_ordinal":adopted["ordinal"],"continuity_ordinal":current["ordinal"]}
    if (delta != 0 or current["generation_digest"] != adopted["generation_digest"]) and not (tail and delta == 1):
        raise ValueError("continuity_adoption_alignment_invalid")
    try: found = _discover(cfg, adopted, wake_adoption)
    except RuntimeError as exc: return {"schema_version":RESULT_SCHEMA,"status":str(exc),"effect_count":0}
    if found is None:
        head = publication._git_text("git", Path(cfg["repository_root"]), ["rev-parse", "HEAD"])
        if head != adopted["base_sha"]: raise ValueError("unexplained_repository_advancement")
        return {"schema_version":RESULT_SCHEMA,"status":"waiting_for_maintenance_closure","effect_count":0}
    task, snap, source = found; now = evaluation_time or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    identity = {"lineage_id":adopted["lineage_id"],"adopted_ordinal":adopted["ordinal"],"adopted_generation_digest":adopted["generation_digest"],"task_id":task,"closure_event_digest":snap["last_event_digest"],"evaluation_time":now}
    if tail:
        identity = {k:tail[0][k] for k in identity}; now = identity["evaluation_time"]
        if identity["task_id"] != task or identity["closure_event_digest"] != snap["last_event_digest"]: raise ValueError("pending_transition_identity_conflict")
    if not tail: _append(cfg, PHASES[0], identity); effects.append("transition_intent_recorded"); phase=1
    else: phase=len(tail)
    out = Path(cfg["evidence_root"])/f"generation-{adopted['ordinal']:06d}"/task
    p=source["paths"]; completion={"schema_version":continuity.CANONICAL_COMPLETION_SCHEMA,"evidence_id":f"{task}:completion:v2","evidence_digest":"","generation_digest":adopted["generation_digest"],"task_id":task,"repository_root":cfg["repository_root"],"state_root":str(source["state_root"].resolve()),"journal_path":p["journal_path"],"journal_digest":publication.bytes_digest(Path(p["journal_path"]).read_bytes()),"lease_path":p["lease_path"],"lease_digest":source["lease"]["lease_digest"],"validation_result_path":p["validation_result_path"],"validation_evidence_digest":source["validation"]["result_digest"],"commit_plan_path":p["commit_plan_path"],"commit_plan_digest":source["plan"]["plan_digest"],"commit_result_path":p["commit_result_path"],"commit_evidence_digest":source["commit"]["commit_result_digest"],"publication_request_path":p["publication_request_path"],"publication_request_digest":source["request"]["publication_request_digest"],"landing_result_path":p["landing_result_path"],"landing_evidence_digest":source["result"]["publication_result_digest"],"closure_event_digest":snap["last_event_digest"]}
    completion["evidence_digest"]=continuity.digest(completion,"evidence_digest")
    successor={"schema_version":continuity.CANONICAL_SUCCESSOR_SCHEMA,"evidence_id":f"{task}:successor:v2","evidence_digest":"","completion_evidence_digest":completion["evidence_digest"],"landing_result_path":p["landing_result_path"],"landing_evidence_digest":source["result"]["publication_result_digest"],"repository_root":cfg["repository_root"],"base_ref":source["result"]["local_base_ref"],"predecessor_base_sha":adopted["base_sha"],"successor_sha":source["result"]["commit_sha"],"observed_at":now}
    successor["evidence_digest"]=continuity.digest(successor,"evidence_digest")
    cp,sp=out/"completion-v2.json",out/"successor-v2.json"; _write(cp,completion); _write(sp,successor)
    if phase == 1: _append(cfg,PHASES[1],identity,completion_adapter_digest=completion["evidence_digest"],successor_adapter_digest=successor["evidence_digest"]); phase=2
    if phase == 2: _append(cfg,PHASES[2],identity,completion_adapter_digest=completion["evidence_digest"],successor_adapter_digest=successor["evidence_digest"]); phase=3
    if paused:
        # The exact generation/receipt pair was already effected before pause.
        # Reconstruct its result without invoking an authority-bearing writer.
        derived_receipt = continuity._closed(continuity._load(continuity._receipt_path(policy, current["ordinal"])), continuity.RECEIPT_SCHEMA, continuity.RECEIPT_KEYS, "receipt_digest")
        if (derived_receipt["predecessor_generation_digest"] != adopted["generation_digest"] or
                derived_receipt["completion_evidence_digest"] != completion["evidence_digest"] or
                derived_receipt["successor_evidence_digest"] != successor["evidence_digest"]):
            raise ValueError("pending_derived_generation_binding_conflict")
        result={"status":"successor_generation_ready","generation_digest":current["generation_digest"],"receipt_digest":derived_receipt["receipt_digest"]}
    else:
        result=continuity.derive_next(cfg["continuity_policy_path"],cp,sp,now)
    if result["status"] != "successor_generation_ready": raise ValueError("continuity_derivation_failed:"+",".join(result.get("reason_codes",[])))
    if phase == 3:
        receipt={"schema_version":RECEIPT_SCHEMA,"receipt_digest":"","config_digest":cfg["config_digest"],**identity,"completion_adapter_path":str(cp),"completion_adapter_digest":completion["evidence_digest"],"successor_adapter_path":str(sp),"successor_adapter_digest":successor["evidence_digest"],"successor_sha":successor["successor_sha"],"resulting_generation_ordinal":adopted["ordinal"]+1,"resulting_generation_digest":result["generation_digest"],"continuity_receipt_digest":result["receipt_digest"],"prior_auto_receipt_digest":next((r.get("auto_receipt_digest",ZERO_DIGEST) for r in reversed(_events(cfg)) if r["event_type"]==PHASES[3]),ZERO_DIGEST)}
        receipt["receipt_digest"]=digest(receipt,"receipt_digest"); rp=Path(cfg["state_root"])/"receipts"/f"receipt-{adopted['ordinal']+1}.json"; _write(rp,receipt)
        _append(cfg,PHASES[3],identity,auto_receipt_path=str(rp),auto_receipt_digest=receipt["receipt_digest"],continuity_generation_digest=result["generation_digest"])
    return {"schema_version":RESULT_SCHEMA,"status":"successor_generation_derived","effect_count":1,"task_id":task,"successor_ordinal":adopted["ordinal"]+1,"generation_digest":result["generation_digest"],"resident_code_adoption_performed":False,"wake_handoff_performed":False,"git_operations_performed":0,"network_performed":False}

class MaintenanceAuthorityContinuityAutoDerivationOwner:
    def __init__(self, config: Mapping[str, Any], *, clock: Callable[[], datetime]=lambda:datetime.now(timezone.utc), waiter: Callable[[threading.Event,float],bool]=lambda e,s:e.wait(s)) -> None:
        self.config=validate_config(config); self._clock=clock; self._waiter=waiter; self._stop=threading.Event(); self._thread:threading.Thread|None=None; self._guard=threading.Lock(); self._health={"status":"configured" if self.config["enabled"] else "disabled","read_only":True}
    def health(self)->dict[str,Any]:
        with self._guard:return dict(self._health)
    def _set(self,status:str,**fields:Any)->None:
        with self._guard:self._health={"status":status,"read_only":True,**fields}
    def start(self)->bool:
        if not self.config["enabled"]:return False
        self._thread=threading.Thread(target=self._run,name="sentientosd-maintenance-continuity-auto",daemon=True);self._thread.start();return True
    def _run(self)->None:
        began=time.monotonic(); count=0
        while not self._stop.is_set() and count<self.config["maximum_successful_derivations"] and time.monotonic()-began<self.config["maximum_wall_clock_seconds"]:
            try:
                result=derive_once(self.config,evaluation_time=self._clock().isoformat().replace("+00:00","Z")); self._set(result["status"],**{k:v for k,v in result.items() if k not in {"status","schema_version"}}); count+=int(result["status"]=="successor_generation_derived")
            except (OSError,ValueError,KeyError,json.JSONDecodeError) as exc:self._set("blocked",reason=str(exc),terminal=True);return
            except Exception as exc:self._set("degraded",reason=str(exc),terminal=True);return
            if self._waiter(self._stop,float(self.config["observation_interval_seconds"])):break
    def stop(self)->bool:
        self._set("shutdown_requested");self._stop.set()
        if self._thread:self._thread.join(float(self.config["shutdown_timeout_seconds"]))
        if self._thread and self._thread.is_alive():self._set("bounded_shutdown_timeout");return False
        return True

def inspect(config: Mapping[str, Any])->dict[str,Any]:
    cfg=validate_config(config); adopted,_=adoption.reconstruct_current(adoption.load_config(cfg["successor_adoption_config_path"])); policy=continuity.validate_policy(_load(cfg["continuity_policy_path"])); current=continuity._current_generation(policy)
    return {"schema_version":RESULT_SCHEMA,"status":"auto_derivation_ready","lineage_id":adopted["lineage_id"],"adopted_ordinal":adopted["ordinal"],"adopted_generation_digest":adopted["generation_digest"],"continuity_ordinal":current["ordinal"],"continuity_generation_digest":current["generation_digest"],"event_count":len(_events(cfg)),"resident_code_adoption_performed":False}
def inspect_receipts(config: Mapping[str, Any])->dict[str,Any]:
    result=inspect(config);result["receipt_count"]=sum(e["event_type"]==PHASES[3] for e in _events(validate_config(config)));return result
doctor=inspect

__all__=["CONFIG_SCHEMA","EVENT_SCHEMA","RECEIPT_SCHEMA","RESULT_SCHEMA","PHASES","MaintenanceAuthorityContinuityAutoDerivationOwner","validate_config","load_config","derive_once","inspect","inspect_receipts","doctor"]
