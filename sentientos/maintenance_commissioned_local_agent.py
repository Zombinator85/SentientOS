"""Lease-bound implementation sessions driven only by commissioned local inference.

The model proposes one JSON action at a time.  This module, not the model, owns
workspace resolution, effects, budgets, cancellation, and terminal classification.
It deliberately has no Codex, provider, commit, or publication path.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from sentientos import maintenance_implementation_agent as mia
from sentientos import maintenance_local_codex_foreman as custody
from sentientos import maintenance_task_authority_lease as leases
from sentientos.governed_local_model_invocation import GovernedLocalModelInvoker, LocalModelInvocationBudget

PURPOSE = "maintenance_implementation"
RESULT_SCHEMA = "sentientos.maintenance_commissioned_local_agent_result:v1"
TOOL_NAMES = frozenset({"read_file", "search_text", "list_path", "replace_file", "run_allowed_command", "git_diff", "git_status"})
TERMINAL_ACTIONS = frozenset({"candidate_complete", "blocked"})
REQUIRED_AUTHORITIES = frozenset({"implementation_agent_session", "implementation_instruction_disclosure", "repository_state_read", "repository_workspace_provision", "repository_workspace_modify", "filesystem_read", "filesystem_write"})
COMMAND_PREFIXES = (("python", "-m", "scripts.run_tests"), ("python", "-m", "pytest"), ("python", "-m", "mypy"), ("python", "-m", "ruff"))
MAX_ACTION_BYTES = 32_768


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


@dataclass(frozen=True)
class LocalAgentBounds:
    max_iterations: int = 24
    max_parse_errors: int = 3
    max_input_chars: int = 24_000
    max_output_chars: int = 8_000
    max_new_tokens_per_call: int = 1_024
    max_total_new_tokens: int = 12_288
    inference_timeout_seconds: float = 60.0
    session_timeout_seconds: float = 900.0
    command_timeout_seconds: float = 120.0
    max_file_read_bytes: int = 64_000
    max_observation_bytes: int = 32_000
    max_directory_entries: int = 200


@dataclass
class CommissionedLocalSession:
    session_id: str
    task_id: str
    correlation_id: str
    lease_id: str
    exact_base: str
    worktree: Mapping[str, Any]
    model_identity: Mapping[str, Any]
    implementation_brief: str
    bounds: LocalAgentBounds
    observations: list[Mapping[str, Any]] = field(default_factory=list)
    validation_feedback: list[Mapping[str, Any]] = field(default_factory=list)
    iterations: int = 0
    token_budget_used: int = 0
    parse_errors: int = 0
    terminal_state: str | None = None
    started_monotonic: float = field(default_factory=time.monotonic)


class CommissionedLocalDriver:
    """ImplementationAgent descriptor plus deterministic local agent loop."""
    driver_id = "commissioned_local_model"
    driver_version = "1"

    def __init__(self, invoker: GovernedLocalModelInvoker, *, bounds: LocalAgentBounds | None = None) -> None:
        self.invoker = invoker
        self.bounds = bounds or LocalAgentBounds()
        self._cancelled: set[str] = set()
        self._lock = threading.Lock()

    def describe_driver(self) -> Mapping[str, Any]:
        d = {"schema_version": mia.DRIVER_SCHEMA, "driver_id": self.driver_id,
             "driver_kind": "commissioned_local", "driver_version": self.driver_version,
             "supported_session_modes": ["mediated_tool_loop"],
             "effect_class": "bounded_repository_workspace_effect",
             "supports_external_session": True, "supports_polling": False,
             "supports_cancellation": True, "supports_recovery": True,
             "supports_corrective_continuation": True,
             "supports_repository_workspace_effects": True,
             "supports_process_execution": True,
             "supports_bounded_instruction_disclosure": True,
             "supports_remote_model_invocation": False, "performs_validation": False,
             "performs_commit": False, "performs_publication": False,
             "inference_purpose": PURPOSE, "descriptor_digest": ""}
        d["descriptor_digest"] = mia.digest({k: v for k, v in d.items() if k != "descriptor_digest"})
        return d

    def prepare_session(self, request: Mapping[str, Any], session: Mapping[str, Any]) -> Mapping[str, Any]:
        return {"prepared": True, "session_id": session.get("session_id"), "request_digest": request.get("request_digest")}

    def observe_session(self, session: Mapping[str, Any], delivered_steps: int) -> Mapping[str, Any]:
        return {"kind": "interrupt", "terminal_reason": "external_local_agent_runtime_required"}

    def request_cancellation(self, session: Mapping[str, Any], cancellation_reference: str) -> Mapping[str, Any]:
        sid = str(session.get("session_id", ""))
        if not sid or not cancellation_reference:
            raise ValueError("cancellation_identity_required")
        with self._lock:
            self._cancelled.add(sid)
        return {"kind": "interrupt", "terminal_reason": "agent_session_cancelled", "cancellation_reference": cancellation_reference}

    def _is_cancelled(self, sid: str) -> bool:
        with self._lock:
            return sid in self._cancelled

    def run(self, *, config: custody.LocalCodexForemanConfig, lease: Mapping[str, Any],
            request: Mapping[str, Any], session: Mapping[str, Any], artifact_root: Path,
            evaluation_time: str, validation_feedback: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
        req = mia.verify_request(request)
        if req["driver_kind"] != "commissioned_local" or req["driver_id"] != self.driver_id:
            return self._terminal("implementation_failed", session, reason="backend_identity_mismatch")
        verified = leases.verify_lease(config.external_state_root, str(lease.get("lease_id", "")),
                                       evaluation_time=evaluation_time, repo_root=config.repository_root)
        if verified.get("status") != "lease_active" or req.get("lease_digest") != lease.get("lease_digest"):
            return self._terminal("implementation_blocked", session, reason="lease_not_active")
        missing = REQUIRED_AUTHORITIES - set(req.get("requested_authority_classes", ()))
        if missing:
            return self._terminal("implementation_blocked", session, reason="missing_effect_authority:" + ",".join(sorted(missing)))
        try:
            worktree = custody.prepare_worktree(config, lease, str(session["session_id"]), recovery=bool(validation_feedback))
            brief = self._read_brief(request, artifact_root, config.maximum_instruction_bytes)
        except (OSError, ValueError, KeyError) as exc:
            return self._terminal("foreman_workspace_invalid", session, reason=str(exc))
        identity = getattr(self.invoker.model, "active_identity", None)
        if identity is None or identity.fallback or identity.posture != "production":
            return self._terminal("implementation_blocked", session, reason="commissioned_model_identity_unavailable")
        state = CommissionedLocalSession(str(session["session_id"]), str(lease["task_id"]),
            "maintenance:" + str(session["session_id"]), str(lease["lease_id"]), str(lease["base_sha"]),
            worktree, identity.to_dict(), brief, self.bounds, validation_feedback=list(validation_feedback))
        return self._loop(config, lease, session, state, evaluation_time)

    def execute(self, *, config: custody.LocalCodexForemanConfig, lease: Mapping[str, Any],
            request: Mapping[str, Any], session: Mapping[str, Any], artifact_root: Path,
            evaluation_time: str, validation_feedback: Sequence[Mapping[str, Any]] = ()) -> Mapping[str, Any]:
        return self.run(config=config,lease=lease,request=request,session=session,
            artifact_root=artifact_root,evaluation_time=evaluation_time,
            validation_feedback=validation_feedback)

    def _read_brief(self, request: Mapping[str, Any], root: Path, maximum: int) -> str:
        ref = str(request.get("external_instruction_artifact_reference") or "instruction.txt")
        base = root.resolve(strict=True); raw_path = base / ref
        if raw_path.is_symlink(): raise ValueError("instruction_artifact_invalid")
        path = raw_path.resolve(strict=True)
        if base not in path.parents or not path.is_file(): raise ValueError("instruction_artifact_invalid")
        raw = path.read_bytes()
        if len(raw) > maximum or request.get("external_instruction_artifact_digest") not in (None, "sha256:" + hashlib.sha256(raw).hexdigest()):
            raise ValueError("instruction_artifact_invalid")
        return raw.decode("utf-8")

    def _loop(self, config: custody.LocalCodexForemanConfig, lease: Mapping[str, Any],
              descriptor: Mapping[str, Any], state: CommissionedLocalSession, evaluation_time: str) -> dict[str, Any]:
        while True:
            terminal = self._bounded_terminal(state)
            if terminal:
                return self._finish(config, lease, descriptor, state, terminal, "resource_or_cancellation_boundary")
            prompt = self._context(state, lease)
            budget = LocalModelInvocationBudget(max_input_chars=state.bounds.max_input_chars,
                max_output_chars=state.bounds.max_output_chars, max_new_tokens=state.bounds.max_new_tokens_per_call,
                timeout_seconds=state.bounds.inference_timeout_seconds, max_calls_per_correlation=state.bounds.max_iterations)
            try:
                req = self.invoker.build_request(purpose=PURPOSE, prompt=prompt,
                    caller="maintenance_commissioned_local_agent", correlation_id=state.correlation_id,
                    lifecycle_phase="runtime", expected_output_format="json", budget=budget,
                    linkage={"task_id": state.task_id, "session_id": state.session_id,
                             "lease_id": state.lease_id, "base_sha": state.exact_base})
                receipt = self.invoker.invoke(req, include_output_in_receipt=False)
            except Exception as exc:
                return self._finish(config, lease, descriptor, state, "implementation_failed", "local_inference_error:" + exc.__class__.__name__)
            state.iterations += 1; state.token_budget_used += state.bounds.max_new_tokens_per_call
            self._audit(config, state, {"kind": "inference", "iteration": state.iterations,
                "request_id": req.request_id, "receipt_id": receipt.receipt_id, "status": receipt.status,
                "model_id": req.model_id, "remote_model_invocation": False})
            if receipt.status != "admitted_completed" or receipt.output_text is None:
                return self._finish(config, lease, descriptor, state, "implementation_failed", "local_inference_" + receipt.status)
            action = self._parse_action(receipt.output_text)
            if action is None:
                state.parse_errors += 1
                state.observations.append({"ok": False, "error": "malformed_action", "no_effect": True})
                continue
            kind = str(action["action"])
            if kind == "blocked":
                return self._finish(config, lease, descriptor, state, "implementation_blocked", str(action.get("reason", "model_reported_blocked")))
            if kind == "candidate_complete":
                return self._finish(config, lease, descriptor, state, "implementation_ready_for_validation", "model_reported_candidate_complete")
            result = self._execute_tool(config, lease, state, kind, action.get("arguments", {}), evaluation_time)
            state.observations.append(result)
            self._audit(config, state, {"kind": "tool", "iteration": state.iterations, "tool": kind,
                "allowed": bool(result.get("ok")), "result_digest": _digest(result), "error": result.get("error")})

    def _bounded_terminal(self, state: CommissionedLocalSession) -> str | None:
        if self._is_cancelled(state.session_id): return "implementation_cancelled"
        if time.monotonic() - state.started_monotonic >= state.bounds.session_timeout_seconds: return "implementation_timed_out"
        if state.iterations >= state.bounds.max_iterations or state.token_budget_used >= state.bounds.max_total_new_tokens: return "implementation_budget_exceeded"
        if state.parse_errors >= state.bounds.max_parse_errors: return "implementation_failed"
        return None

    @staticmethod
    def _parse_action(raw: str) -> dict[str, Any] | None:
        if len(raw.encode()) > MAX_ACTION_BYTES: return None
        try: value = json.loads(raw)
        except (json.JSONDecodeError, UnicodeError): return None
        if not isinstance(value, dict) or set(value) - {"action", "arguments", "reason", "summary"}: return None
        action = value.get("action")
        if action not in TOOL_NAMES | TERMINAL_ACTIONS: return None
        if action in TOOL_NAMES and (not isinstance(value.get("arguments"), dict) or set(value) != {"action", "arguments"}): return None
        return value

    def _safe_path(self, state: CommissionedLocalSession, lease: Mapping[str, Any], raw: Any, *, write: bool = False) -> Path:
        if not isinstance(raw, str) or not raw or Path(raw).is_absolute() or ".." in Path(raw).parts or ".git" in Path(raw).parts:
            raise ValueError("workspace_path_rejected")
        root = Path(str(state.worktree["worktree_root"])).resolve(strict=True)
        candidate = root / raw
        parent = candidate.parent.resolve(strict=True)
        resolved = candidate.resolve(strict=False)
        if (resolved != root and root not in resolved.parents) or (root not in parent.parents and parent != root):
            raise ValueError("workspace_escape_rejected")
        scoped_parents=[]
        cursor=candidate.parent
        while cursor != root:
            scoped_parents.append(cursor); cursor=cursor.parent
        if candidate.is_symlink() or any(p.is_symlink() for p in scoped_parents):
            raise ValueError("workspace_symlink_rejected")
        if write and not any(raw == a.rstrip("/") or raw.startswith(a.rstrip("/") + "/") for a in lease["admitted_subject_paths"]):
            raise ValueError("path_outside_admitted_scope")
        return candidate

    def _execute_tool(self, config: custody.LocalCodexForemanConfig, lease: Mapping[str, Any],
                      state: CommissionedLocalSession, tool: str, args: Any, evaluation_time: str) -> dict[str, Any]:
        if self._is_cancelled(state.session_id): return {"ok": False, "error": "cancelled", "no_effect": True}
        live = leases.verify_lease(config.external_state_root, state.lease_id, evaluation_time=evaluation_time, repo_root=config.repository_root)
        if live.get("status") != "lease_active": return {"ok": False, "error": "lease_not_active", "no_effect": True}
        try:
            root = Path(str(state.worktree["worktree_root"])).resolve(strict=True)
            if tool == "read_file":
                path = self._safe_path(state, lease, args.get("path")); data = path.read_bytes()
                start = max(1, int(args.get("start_line", 1))); count = min(500, max(1, int(args.get("line_count", 200))))
                if len(data) > state.bounds.max_file_read_bytes: data = data[:state.bounds.max_file_read_bytes]
                text = "\n".join(data.decode("utf-8").splitlines()[start-1:start-1+count])
                return self._result({"ok": True, "path": str(args["path"]), "content": text})
            if tool == "list_path":
                path = self._safe_path(state, lease, args.get("path", ".")); entries=[]
                for item in sorted(path.iterdir(), key=lambda p:p.name)[:state.bounds.max_directory_entries]:
                    entries.append({"name": item.name, "type": "symlink" if item.is_symlink() else "dir" if item.is_dir() else "file"})
                return self._result({"ok": True, "path": str(args.get("path", ".")), "entries": entries})
            if tool == "search_text":
                needle=args.get("query")
                if not isinstance(needle,str) or not needle or len(needle)>256: raise ValueError("search_query_rejected")
                base=self._safe_path(state,lease,args.get("path",".")); hits: list[dict[str, Any]]=[]
                candidates=[base] if base.is_file() else sorted(base.rglob("*"))
                for path in candidates:
                    if len(hits)>=100: break
                    if not path.is_file() or path.is_symlink() or ".git" in path.parts: continue
                    try:
                        for number,line in enumerate(path.read_text(errors="replace").splitlines(),1):
                            if needle in line: hits.append({"path":str(path.relative_to(root)),"line":number,"text":line[:500]})
                    except OSError: continue
                return self._result({"ok":True,"hits":hits})
            if tool == "replace_file":
                path=self._safe_path(state,lease,args.get("path"),write=True); content=args.get("content"); expected=args.get("expected_sha256")
                if not isinstance(content,str) or len(content.encode())>state.bounds.max_file_read_bytes: raise ValueError("replacement_rejected")
                current=path.read_bytes() if path.exists() else b""; actual=hashlib.sha256(current).hexdigest()
                if expected != actual: raise ValueError("stale_file_content")
                tmp=path.with_name("."+path.name+".maintenance-agent-tmp")
                fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
                try:
                    with os.fdopen(fd,"wb") as handle: handle.write(content.encode()); handle.flush(); os.fsync(handle.fileno())
                    os.replace(tmp,path)
                finally:
                    if tmp.exists(): tmp.unlink()
                return {"ok":True,"path":str(args["path"]),"content_sha256":hashlib.sha256(content.encode()).hexdigest()}
            if tool in {"git_status","git_diff"}:
                argv=[str(config.git_executable), "status", "--porcelain=v1", "--untracked-files=all"] if tool=="git_status" else [str(config.git_executable),"diff","--no-ext-diff","--","."]
                cp=subprocess.run(argv,cwd=root,text=True,capture_output=True,shell=False,timeout=state.bounds.command_timeout_seconds,env=self._environment())
                return self._result({"ok":cp.returncode==0,"returncode":cp.returncode,"stdout":cp.stdout,"stderr":cp.stderr})
            if tool == "run_allowed_command":
                argv=args.get("argv")
                if not isinstance(argv,list) or not argv or not all(isinstance(x,str) and 0<len(x)<=500 for x in argv): raise ValueError("command_rejected")
                normalized=tuple("python" if i==0 and Path(x).name.startswith("python") else x for i,x in enumerate(argv))
                if not any(normalized[:len(prefix)]==prefix for prefix in COMMAND_PREFIXES): raise ValueError("command_not_allowed")
                cp=subprocess.run(argv,cwd=root,text=True,capture_output=True,shell=False,timeout=state.bounds.command_timeout_seconds,env=self._environment())
                return self._result({"ok":cp.returncode==0,"argv":argv,"returncode":cp.returncode,"stdout":cp.stdout,"stderr":cp.stderr})
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            return {"ok":False,"error":str(exc),"no_effect":True}
        return {"ok":False,"error":"unsupported_tool","no_effect":True}

    def _result(self, value: Mapping[str, Any]) -> dict[str, Any]:
        raw=json.dumps(value,sort_keys=True)
        if len(raw.encode())<=self.bounds.max_observation_bytes: return dict(value)
        return {"ok":value.get("ok",False),"truncated":True,"observation":raw.encode()[:self.bounds.max_observation_bytes].decode("utf-8","ignore")}

    @staticmethod
    def _environment() -> dict[str, str]:
        keep={k:v for k,v in os.environ.items() if k in {"PATH","LANG","LC_ALL","TMPDIR"}}
        keep.update({"PYTHONDONTWRITEBYTECODE":"1","NO_PROXY":"*","HTTP_PROXY":"","HTTPS_PROXY":"","ALL_PROXY":""})
        return keep

    def _context(self, state: CommissionedLocalSession, lease: Mapping[str, Any]) -> str:
        payload={"protocol":"Return exactly one JSON object. Tool: {action:<tool>,arguments:{...}}. Terminal: {action:candidate_complete,summary:<text>} or {action:blocked,reason:<text>}.",
            "implementation_brief":state.implementation_brief,"session":{"session_id":state.session_id,"task_id":state.task_id,"base_sha":state.exact_base,"model_identity":state.model_identity,"lease_id":state.lease_id},
            "authority_boundary":"You propose actions only. The runtime executes allowed effects. You cannot validate, commit, publish, use network, or grant authority.",
            "allowed_tools":sorted(TOOL_NAMES),"admitted_paths":lease["admitted_subject_paths"],"iteration":state.iterations+1,
            "remaining":{"iterations":state.bounds.max_iterations-state.iterations,"token_budget":state.bounds.max_total_new_tokens-state.token_budget_used},
            "recent_observations":state.observations[-6:],"validation_feedback":state.validation_feedback[-2:]}
        return json.dumps(payload,sort_keys=True,separators=(",",":"))

    def _finish(self, config: custody.LocalCodexForemanConfig, lease: Mapping[str, Any], descriptor: Mapping[str, Any], state: CommissionedLocalSession, status: str, reason: str) -> dict[str, Any]:
        state.terminal_state=status
        manifest=custody.changed_manifest(config,lease,state.worktree)
        if status=="implementation_ready_for_validation" and (not manifest["changed_paths"] or manifest["out_of_scope_paths"] or manifest["forbidden_paths"] or manifest["budget_findings"] or manifest["terminal_head"]!=lease["base_sha"]):
            status="implementation_no_change" if not manifest["changed_paths"] else "implementation_scope_violated"
        result={"schema_version":RESULT_SCHEMA,"status":status,"reason_codes":[reason],"task_id":state.task_id,"session_id":state.session_id,"lease_id":state.lease_id,"base_sha":state.exact_base,"driver_id":self.driver_id,"driver_kind":"commissioned_local","model_identity":state.model_identity,"correlation_id":state.correlation_id,"worktree_id":state.worktree["worktree_id"],"worktree_descriptor_digest":state.worktree["worktree_digest"],"change_manifest_digest":manifest["manifest_digest"],"changed_paths":manifest["changed_paths"],"iteration_count":state.iterations,"token_budget_used_upper_bound":state.token_budget_used,"validation_feedback_count":len(state.validation_feedback),"effects":{"local_model_inference_performed":state.iterations>0,"remote_model_invocation_performed":False,"codex_invocation_performed":False,"repository_mutation_performed":bool(manifest["changed_paths"]),"validation_performed":False,"git_commit_performed":False,"publication_performed":False,"unauthorized_host_effect_performed":False},"result_digest":""}
        result["result_digest"]=_digest({k:v for k,v in result.items() if k!="result_digest"})
        custody.write_json(config.external_state_root/"maintenance_commissioned_local_results"/(state.session_id+".json"), result, immutable=False)
        self._audit(config,state,{"kind":"terminal","status":status,"reason":reason,"result_digest":result["result_digest"],"change_manifest_digest":manifest["manifest_digest"]})
        return result

    def _terminal(self, status: str, session: Mapping[str, Any], *, reason: str) -> dict[str, Any]:
        result={"schema_version":RESULT_SCHEMA,"status":status,"reason_codes":[reason],"session_id":session.get("session_id"),"driver_id":self.driver_id,"driver_kind":"commissioned_local","effects":{"remote_model_invocation_performed":False,"codex_invocation_performed":False,"validation_performed":False,"git_commit_performed":False,"publication_performed":False},"result_digest":""}
        result["result_digest"]=_digest({k:v for k,v in result.items() if k!="result_digest"}); return result

    def _audit(self, config: custody.LocalCodexForemanConfig, state: CommissionedLocalSession, event: Mapping[str, Any]) -> None:
        root=config.external_state_root/"maintenance_commissioned_local_sessions"; root.mkdir(parents=True,exist_ok=True)
        path=root/(state.session_id+".jsonl")
        record={"session_id":state.session_id,"task_id":state.task_id,"lease_id":state.lease_id,"correlation_id":state.correlation_id,"model_identity":state.model_identity,"event":dict(event)}
        with path.open("a",encoding="utf-8") as handle: handle.write(json.dumps(record,sort_keys=True,separators=(",",":"))+"\n")
