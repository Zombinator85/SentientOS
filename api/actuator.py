from __future__ import annotations
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from sentientos.privilege import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.

from logging_config import get_log_path
import os
import json
import re
import subprocess
import smtplib
import threading
import time
import queue
from email.message import EmailMessage
from pathlib import Path
import autonomous_audit as aa

try:
    import requests  # type: ignore  # HTTP requests
except Exception:  # pragma: no cover - fallback when requests isn't installed
    requests = None

try:
    import yaml  # type: ignore  # YAML config
except Exception:  # pragma: no cover - fallback when PyYAML isn't installed
    yaml = None
import ast
from typing import Any, Dict, Callable

# --- Pluggable actuator registry -------------------------------------------

class BaseActuator:
    """Interface for pluggable actuator types."""

    def execute(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


ACTUATORS: dict[str, BaseActuator] = {}
PLUGINS_INFO: dict[str, str] = {}
_LOADED_PLUGIN_FILES: list[Path] = []

AUTONOMOUS_LOG = get_log_path("autonomous_calls.jsonl", "AUTONOMOUS_CALLS_LOG")
AUTONOMOUS_LOG.parent.mkdir(parents=True, exist_ok=True)


def register_actuator(name: str, actuator: BaseActuator) -> None:
    ACTUATORS[name] = actuator


def load_plugins() -> None:
    """Load actuator plugins from the plugins directory."""
    global PLUGINS_INFO, _LOADED_PLUGIN_FILES
    PLUGINS_INFO = {}
    plugins_dir = Path(os.getenv("ACT_PLUGINS_DIR", "plugins"))
    if not plugins_dir.exists():
        return
    _LOADED_PLUGIN_FILES = list(plugins_dir.glob("*.py"))
    for fp in _LOADED_PLUGIN_FILES:
        spec: dict[str, Any] = {}
        with open(fp, "r", encoding="utf-8") as f:
            code = f.read()
        try:
            exec(compile(code, str(fp), "exec"), spec)
        except Exception:
            continue
        reg = spec.get("register")
        if callable(reg):
            try:
                reg(register_actuator)
            except Exception:
                pass
        PLUGINS_INFO[fp.stem] = (spec.get("__doc__") or "").strip()


def list_plugins() -> dict[str, str]:
    """Return mapping of plugin name to docstring."""
    return dict(PLUGINS_INFO)


def reload_plugins() -> None:
    """Reload actuator plugins from disk."""
    for name in list(ACTUATORS.keys()):
        if name not in {"shell", "http", "file", "email", "webhook"}:
            ACTUATORS.pop(name, None)
    load_plugins()


from memory_manager import write_mem, save_reflection

# Load whitelist
WHITELIST_PATH = Path(os.getenv("ACT_WHITELIST", "config/act_whitelist.yml"))
TEMPLATES_PATH = Path(os.getenv("ACT_TEMPLATES", "config/act_templates.yml"))
def _load_yaml(text: str):
    if yaml:
        return yaml.safe_load(text)
    data = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if ':' not in line:
            continue
        key, val = line.split(':', 1)
        key = key.strip()
        val = val.strip()
        if val.startswith('[') and val.endswith(']'):
            data[key] = ast.literal_eval(val)
        else:
            try:
                data[key] = int(val)
            except ValueError:
                data[key] = val
    return data

if WHITELIST_PATH.exists():
    WHITELIST = _load_yaml(WHITELIST_PATH.read_text()) or {}
else:
    WHITELIST = {"shell": [], "http": [], "timeout": 30}

SANDBOX_DIR = Path(os.getenv("ACT_SANDBOX", "sandbox"))
SANDBOX_DIR.mkdir(exist_ok=True)


class ShellActuator(BaseActuator):
    def execute(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        return run_shell(intent.get("cmd", ""), cwd=intent.get("cwd", "."))


class HttpActuator(BaseActuator):
    def execute(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        url = intent.get("url", "")
        method = intent.get("method", "GET")
        extras = {k: v for k, v in intent.items() if k not in {"type", "url", "method"}}
        return http_fetch(url, method=method, **extras)


class FileActuator(BaseActuator):
    def execute(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        return file_write(intent.get("path", ""), intent.get("content", ""))


class EmailActuator(BaseActuator):
    def execute(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        return send_email(intent.get("to", ""), intent.get("subject", ""), intent.get("body", ""))


class WebhookActuator(BaseActuator):
    def execute(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        return trigger_webhook(intent.get("url", ""), intent.get("payload", {}))


class WorkflowActuator(BaseActuator):
    """Execute a registered workflow via ``workflow_controller``."""

    def execute(self, intent: Dict[str, Any]) -> Dict[str, Any]:
        name = intent.get("name")
        if not name:
            raise ValueError("workflow name required")
        import workflow_controller as wc

        ok = wc.run_workflow(name)
        return {"ok": ok}


def register_builtin_actuators() -> None:
    register_actuator("shell", ShellActuator())
    register_actuator("http", HttpActuator())
    register_actuator("file", FileActuator())
    register_actuator("email", EmailActuator())
    register_actuator("webhook", WebhookActuator())
    register_actuator("workflow", WorkflowActuator())


register_builtin_actuators()
load_plugins()


def _match_patterns(value: str, patterns: list[str]) -> bool:
    for pat in patterns:
        if pat.startswith('^'):
            if re.match(pat, value):
                return True
        else:
            import fnmatch
            if '*' in pat or '?' in pat:
                if fnmatch.fnmatch(value, pat):
                    return True
            else:
                if value.startswith(pat):
                    return True
    return False

def _allowed_shell(cmd: str) -> bool:
    first = cmd.strip().split()[0] if cmd.strip() else ""
    patterns = WHITELIST.get("shell", [])
    return _match_patterns(first, patterns)

def run_shell(cmd: str, cwd: str = ".") -> dict:
    if not _allowed_shell(cmd):
        raise PermissionError("Command not allowed")
    cwd_path = _safe_path(cwd if cwd != "." else "")
    res = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        cwd=str(cwd_path),
        timeout=WHITELIST.get("timeout", 30),
    )
    return {
        "code": res.returncode,
        "stdout": res.stdout,
        "stderr": res.stderr,
    }

def http_fetch(url: str, method: str = "GET", **kwargs) -> dict:
    patterns = WHITELIST.get("http", [])
    if not _match_patterns(url, patterns):
        raise PermissionError("URL not allowed")
    timeout = WHITELIST.get("timeout", 30)
    if requests:
        resp = requests.request(method, url, timeout=timeout, **kwargs)
        return {"status": resp.status_code, "text": resp.text}
    import urllib.request
    req = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        text = r.read().decode()
        status = r.getcode()
    return {"status": status, "text": text}

def _safe_path(rel: str) -> Path:
    target = (SANDBOX_DIR / rel).resolve()
    if not str(target).startswith(str(SANDBOX_DIR.resolve())):
        raise PermissionError("Path escapes sandbox")
    return target


def file_write(path: str, content: str) -> dict:
    target = _safe_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return {"written": str(target)}


def send_email(to: str, subject: str, body: str) -> dict:
    host = os.getenv("SMTP_HOST")
    if not host:
        raise EnvironmentError("SMTP not configured")
    port = int(os.getenv("SMTP_PORT", "25"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")
    from_addr = os.getenv("SMTP_FROM", user or "noreply@example.com")
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(host, port) as smtp:
        if user and password:
            smtp.login(user, password)
        smtp.send_message(msg)
    return {"sent": to}


def trigger_webhook(url: str, payload: dict) -> dict:
    patterns = WHITELIST.get("http", [])
    if not _match_patterns(url, patterns):
        raise PermissionError("URL not allowed")
    if requests:
        resp = requests.post(url, json=payload, timeout=WHITELIST.get("timeout", 30))
        return {"status": resp.status_code}
    import urllib.request
    import json as _json
    data = _json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=WHITELIST.get("timeout", 30)) as r:
        status = r.getcode()
    return {"status": status}


TEMPLATES = {}
if TEMPLATES_PATH.exists():
    TEMPLATES = _load_yaml(TEMPLATES_PATH.read_text()) or {}


# --- Async handling ---------------------------------------------------------
TASK_QUEUE: "queue.Queue[tuple[str, Dict[str, Any], str | None, str | None]]" = queue.Queue()
ACTION_STATUS: dict[str, dict] = {}
_worker_started = False


def _worker() -> None:
    while True:
        action_id, intent, explanation, user = TASK_QUEUE.get()
        ACTION_STATUS[action_id] = {"status": "running"}
        try:
            result = act(intent, explanation=explanation, user=user)
            ACTION_STATUS[action_id] = {"status": "finished", "result": result}
        except Exception as e:  # pragma: no cover - defensive
            ACTION_STATUS[action_id] = {"status": "failed", "error": str(e)}
        TASK_QUEUE.task_done()


def start_async(intent: Dict[str, Any], explanation: str | None = None, user: str | None = None) -> str:
    """Queue an action for background execution and return its id."""
    global _worker_started
    action_id = f"a{int(time.time()*1000)}"
    ACTION_STATUS[action_id] = {"status": "queued"}
    TASK_QUEUE.put((action_id, intent, explanation, user))
    if not _worker_started:
        threading.Thread(target=_worker, daemon=True).start()
        _worker_started = True
    return action_id


def get_status(action_id: str) -> dict:
    return ACTION_STATUS.get(action_id, {"status": "unknown"})


def expand_template(name: str, params: dict) -> dict:
    tpl = TEMPLATES.get(name)
    if not tpl:
        raise ValueError("Unknown template")
    if isinstance(tpl, str):
        tpl = tpl.format(**params)
        return json.loads(tpl)
    out = json.loads(json.dumps(tpl))  # deep copy
    for k, v in out.items():
        if isinstance(v, str):
            out[k] = v.format(**params)
    return out


def template_placeholders(name: str) -> set[str]:
    """Return placeholder fields required by a template."""
    tpl = TEMPLATES.get(name)
    if not tpl:
        raise ValueError("Unknown template")
    import string

    def collect(obj) -> set[str]:
        keys: set[str] = set()
        if isinstance(obj, str):
            for _, field, _, _ in string.Formatter().parse(obj):
                if field:
                    keys.add(field)
        elif isinstance(obj, dict):
            for v in obj.values():
                keys.update(collect(v))
        return keys

    return collect(tpl)

def dispatch(intent: dict) -> dict:
    itype = intent.get("type")
    if itype == "template":
        expanded = expand_template(intent.get("name", ""), intent.get("params", {}))
        return dispatch(expanded)
    act = ACTUATORS.get(itype)
    if not act:
        raise ValueError("Unsupported intent")
    return act.execute(intent)


LAST_EXECUTION: dict[tuple[str, str], float] = {}
RATE_LIMIT_SECONDS = int(os.getenv("ACT_RATE_LIMIT", "5"))


def _rate_limit(intent: Dict[str, Any], user: str | None) -> None:
    key = (user or "", intent.get("type") + ":" + intent.get("name", ""))
    now = time.time()
    last = LAST_EXECUTION.get(key, 0)
    if now - last < RATE_LIMIT_SECONDS:
        raise RuntimeError("Rate limit exceeded")
    LAST_EXECUTION[key] = now


CRITIQUE_STEPS = [
    lambda i, e: f"Action {i.get('type')} failed with {e}. Try again with adjusted parameters.",
    lambda i, e: f"Repeated failure for {i.get('type')}. Verify permissions or inputs before retrying.",
    lambda i, e: f"Escalation: manual intervention required for {i.get('type')}" ,
]


def _auto_critique(intent: Dict[str, Any], error: Exception, step: int = 0) -> tuple[str, int]:
    """Return critique text and next step index."""
    idx = min(step, len(CRITIQUE_STEPS) - 1)
    critique = CRITIQUE_STEPS[idx](intent, error)
    next_step = idx + 1 if idx + 1 < len(CRITIQUE_STEPS) else idx
    return critique, next_step


def act(
    intent: Dict[str, Any],
    explanation: str | None = None,
    user: str | None = None,
    dry_run: bool | None = None,
    critique_step: int | None = None,
) -> Dict[str, Any]:
    """Execute an intent and persist a log entry.

    Parameters
    ----------
    intent: mapping describing the action. Keys depend on the ``type`` field.
    explanation: optional reason for choosing the action.
    """
    if dry_run is None:
        dry_run = intent.pop("dry_run", False)
    try:
        _rate_limit(intent, user)
        if dry_run:
            result = {"dry_run": True, "intent": intent}
        else:
            result = dispatch(intent)
        reflection_text = (
            f"Action {intent.get('type')} {'dry run' if dry_run else 'executed'} successfully"
        )
        log_entry = {
            "intent": intent,
            "result": result,
            "explanation": explanation or "",
            "user": user or "",
            "status": "finished",
            "reflection": reflection_text,
        }
        log_id = write_mem(json.dumps(log_entry), tags=["act", intent.get("type", "")], source="actuator")
        reflection_id = save_reflection(
            parent=log_id,
            intent=intent,
            result=result,
            reason=explanation or "",
            user=user or "",
            plugin=intent.get("type", ""),
        )
        result = dict(result)
        result.update({"log_id": log_id, "status": "finished", "reflection": reflection_text, "reflection_id": reflection_id})
        if explanation:
            result["explanation"] = explanation
        return result
    except Exception as e:  # pragma: no cover - defensive
        reflection_text = f"Action {intent.get('type')} failed: {e}"
        step = critique_step if critique_step is not None else intent.pop("_critique_step", 0)
        critique, next_step = _auto_critique(intent, e, step)
        err_entry = {
            "intent": intent,
            "error": str(e),
            "explanation": explanation or "",
            "user": user or "",
            "status": "failed",
            "reflection": reflection_text,
        }
        log_id = write_mem(json.dumps(err_entry), tags=["act", "error"], source="actuator")
        reflection_id = save_reflection(
            parent=log_id,
            intent=intent,
            result=None,
            reason=str(e),
            next_step=critique,
            user=user or "",
            plugin=intent.get("type", ""),
        )
        return {
            "error": str(e),
            "log_id": log_id,
            "status": "failed",
            "reflection": reflection_text,
            "critique": critique,
            "critique_step": next_step,
            "reflection_id": reflection_id,
        }


def auto_call(
    intent: Dict[str, Any],
    explanation: str | None = None,
    *,
    trace: str | None = None,
) -> Dict[str, Any]:
    """Execute an intent and log it to the autonomous call history."""
    result = act(intent, explanation=explanation, user="auto")
    aa.log_entry(
        action=json.dumps(intent),
        rationale=explanation or "auto_call",
        memory=[result.get("log_id")] if isinstance(result, dict) and result.get("log_id") else [],
        expected=str(result),
        why_chain=[
            "Auto-call dispatched intent", 
            "Auto-call invoked by autonomous subsystem", 
            "Fragment logged for trace"
        ],
    )
    entry = {
        "timestamp": time.time(),
        "intent": intent,
        "result": result,
        "trace": trace,
    }
    with open(AUTONOMOUS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return result


def recent_logs(last: int = 10, reflect: bool = False) -> list[dict]:
    from memory_manager import RAW_PATH, recent_reflections
    files = sorted(RAW_PATH.glob("*.json"))
    refl_map = {}
    if reflect:
        for r in recent_reflections(limit=last * 2):
            refl_map[r.get("parent")] = r
    out = []
    for fp in reversed(files):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if "act" not in data.get("tags", []):
            continue
        try:
            entry = json.loads(data.get("text", "{}"))
            entry["timestamp"] = data.get("timestamp")
            entry["id"] = data.get("id")
            if "intent" not in entry:
                continue
            if reflect:
                entry["reflection_text"] = entry.get("reflection", "")
                if entry["id"] in refl_map:
                    r = refl_map[entry["id"]]
                    entry["reflection_text"] = (
                        r.get("reason") or r.get("next") or entry.get("reflection", "")
                    )
            out.append(entry)
            if len(out) >= last:
                break
        except Exception:
            continue
    return out


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="SentientOS actuator CLI")
    parser.add_argument(
        "subcommand",
        choices=[
            "shell",
            "http",
            "write",
            "email",
            "webhook",
            "template",
            "template_help",
            "logs",
            "templates",
            "plugins",
        ],
        help="Action type",
    )
    parser.add_argument("cmd", nargs="?", help="Shell command when subcommand=shell")
    parser.add_argument("--url", dest="url", help="URL for http")
    parser.add_argument("--method", dest="method", default="GET")
    parser.add_argument("--data", dest="data")
    parser.add_argument("--file", dest="file")
    parser.add_argument("--text", dest="text")
    parser.add_argument("--to", dest="to")
    parser.add_argument("--subject", dest="subject")
    parser.add_argument("--body", dest="body")
    parser.add_argument("--payload", dest="payload")
    parser.add_argument("--name", dest="name")
    parser.add_argument("--params", dest="params")
    parser.add_argument("--cwd", dest="cwd", default=".")
    parser.add_argument("--why", dest="why")
    parser.add_argument("--dry", action="store_true", help="Dry run")
    parser.add_argument("--reflect", action="store_true", help="Include reflections in logs")
    parser.add_argument("--last", dest="last", type=int, default=10)
    parser.add_argument("--reload", action="store_true", help="Reload plugins")

    args = parser.parse_args(argv)

    if args.subcommand == "templates":
        names = list(TEMPLATES.keys())
        if args.cmd:
            term = args.cmd.lower()
            names = [n for n in names if term in n.lower()]
        print(json.dumps({"templates": names}, indent=2))
        return

    if args.subcommand == "plugins":
        if args.reload:
            reload_plugins()
        print(json.dumps(list_plugins(), indent=2))
        return

    intent: Dict[str, Any] = {"type": args.subcommand if args.subcommand not in {"write", "logs"} else ("file" if args.subcommand == "write" else "logs")}
    if args.subcommand == "shell" and args.cmd:
        intent["cmd"] = args.cmd
        intent["cwd"] = args.cwd
    elif args.subcommand == "http":
        intent.update({"url": args.url or "", "method": args.method})
        if args.data:
            intent["data"] = args.data
    elif args.subcommand == "write":
        intent.update({"path": args.file or "", "content": args.text or ""})
    elif args.subcommand == "email":
        intent.update({"to": args.to or "", "subject": args.subject or "", "body": args.body or ""})
    elif args.subcommand == "webhook":
        payload = json.loads(args.payload or "{}") if args.payload else {}
        intent.update({"url": args.url or "", "payload": payload})
    elif args.subcommand == "template":
        params = json.loads(args.params or "{}") if args.params else {}
        missing = [p for p in template_placeholders(args.name or "") if p not in params]
        for m in missing:
            params[m] = input(f"{m}: ")
        intent.update({"name": args.name or "", "params": params})
    elif args.subcommand == "template_help":
        if args.name:
            fields = template_placeholders(args.name)
            example = {k: f"<{k}>" for k in fields}
            print(json.dumps({"required": sorted(fields), "example": example}, indent=2))
        else:
            print("Specify --name")
        return
    elif args.subcommand == "logs":
        logs = recent_logs(args.last, reflect=args.reflect)
        print(json.dumps(logs, indent=2))
        return

    out = act(intent, explanation=args.why, dry_run=args.dry)
    print(json.dumps(out))


if __name__ == "__main__":  # pragma: no cover - CLI execution
    main()
