import os
import json
import datetime
import importlib
from pathlib import Path
from typing import Callable, Dict, List, Optional, Any, Tuple

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    yaml = None
import ast

import notification
from memory_manager import save_reflection

try:
    from policy_engine import PolicyEngine
except Exception:  # pragma: no cover - optional dependency
    PolicyEngine = None  # type: ignore

MEMORY_DIR = Path(os.getenv("MEMORY_DIR", "logs/memory"))
EVENT_PATH = MEMORY_DIR / "events.jsonl"
EVENT_PATH.parent.mkdir(parents=True, exist_ok=True)


def _load_yaml(text: str) -> Dict[str, Any]:
    if yaml:
        return yaml.safe_load(text)
    data: Dict[str, Any] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key = key.strip()
        val = val.strip()
        if val.startswith("[") and val.endswith("]"):
            data[key] = ast.literal_eval(val)
        else:
            try:
                data[key] = int(val)
            except ValueError:
                data[key] = val
    return data


def _log(event: str, payload: Dict[str, Any]) -> None:
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "event": event,
        "payload": payload,
        "tag": "run:workflow" if event.startswith("workflow") else event,
    }
    with open(EVENT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    notification.send(event, payload)


Step = Dict[str, Any]
WORKFLOWS: Dict[str, List[Step]] = {}
WORKFLOW_FILES: Dict[str, Path] = {}
ACTION_REGISTRY: Dict[str, Callable[..., Any]] = {}
_HISTORY: List[Tuple[str, Step]] = []


def register_action(name: str, fn: Callable[..., Any]) -> None:
    """Register a callable that can be referenced in workflow scripts."""
    ACTION_REGISTRY[name] = fn


def register_workflow(name: str, steps: List[Step]) -> None:
    """Register a workflow consisting of a list of step mappings."""
    WORKFLOWS[name] = steps


def _resolve_callable(name: str) -> Callable[..., Any]:
    if name in ACTION_REGISTRY:
        return ACTION_REGISTRY[name]
    if "." in name:
        mod_name, attr = name.rsplit(".", 1)
        mod = importlib.import_module(mod_name)
        return getattr(mod, attr)
    raise ValueError(f"Unknown action {name}")


def _wrap_action(name: str, params: Optional[Dict[str, Any]] = None) -> Callable[[], Any]:
    def _inner() -> Any:
        fn = _resolve_callable(name)
        return fn(**(params or {}))

    return _inner


def load_workflow_file(path: str) -> None:
    """Load a workflow from a YAML/JSON/Python file."""
    fp = Path(path)
    text = fp.read_text(encoding="utf-8")
    if fp.suffix in {".yaml", ".yml"}:
        data = _load_yaml(text)
    elif fp.suffix == ".json":
        data = json.loads(text)
    elif fp.suffix == ".py":
        spec: Dict[str, Any] = {}
        exec(compile(text, str(fp), "exec"), spec)
        data = spec.get("WORKFLOW", spec)
    else:
        raise ValueError("Unsupported workflow file")
    name = data.get("name", fp.stem)
    steps: List[Step] = []
    for st in data.get("steps", []):
        step = dict(st)
        act = step.get("action")
        if isinstance(act, str):
            step["action"] = _wrap_action(act, step.get("params"))
        undo = step.get("undo")
        if isinstance(undo, str):
            step["undo"] = _wrap_action(undo, step.get("undo_params"))
        of = step.get("on_fail")
        if isinstance(of, str):
            step["on_fail"] = [_wrap_action(of)]
        elif isinstance(of, list):
            step["on_fail"] = [_wrap_action(o) if isinstance(o, str) else o for o in of]
        steps.append(step)
    register_workflow(name, steps)
    WORKFLOW_FILES[name] = fp


def load_workflows(path: str) -> None:
    p = Path(path)
    if p.is_dir():
        for ext in ("*.yml", "*.yaml", "*.json", "*.py"):
            for fp in p.glob(ext):
                load_workflow_file(str(fp))
    else:
        load_workflow_file(str(p))


def _undo_steps(steps: List[Step], wf: str) -> None:
    for step in steps:
        undo = step.get("undo")
        if callable(undo):
            try:
                undo()
                _log("workflow.undo", {"workflow": wf, "step": step.get("name"), "status": "ok"})
            except Exception as e:  # pragma: no cover - defensive
                _log(
                    "workflow.undo",
                    {"workflow": wf, "step": step.get("name"), "status": "failed", "error": str(e)},
                )
        try:
            _HISTORY.remove((wf, step))
        except ValueError:
            pass


def run_workflow(
    name: str,
    *,
    policy_engine: Optional["PolicyEngine"] = None,
    auto_undo: bool = True,
) -> bool:
    steps = WORKFLOWS.get(name, [])
    executed: List[Step] = []
    _log("workflow.start", {"workflow": name})
    for step in steps:
        ev_name = step.get("policy_event") or f"workflow.{name}.{step.get('name', '')}"
        if policy_engine:
            actions = policy_engine.evaluate({"event": ev_name})
            if any(a.get("type") == "deny" for a in actions):
                _log(
                    "workflow.step",
                    {"workflow": name, "step": step.get("name"), "status": "denied"},
                )
                for fn in step.get("on_fail", []):
                    try:
                        fn()
                    except Exception:
                        pass
                if auto_undo:
                    _undo_steps(list(reversed(executed)), name)
                _log("workflow.end", {"workflow": name, "status": "denied"})
                return False
        try:
            fn: Callable[[], Any] = step.get("action", lambda: None)
            fn()
            executed.append(step)
            _HISTORY.append((name, step))
            _log("workflow.step", {"workflow": name, "step": step.get("name"), "status": "ok"})
        except Exception as e:
            _log(
                "workflow.step",
                {"workflow": name, "step": step.get("name"), "status": "failed", "error": str(e)},
            )
            for fn in step.get("on_fail", []):
                try:
                    fn()
                except Exception:
                    pass
            if auto_undo:
                _undo_steps(list(reversed(executed)), name)
            _log("workflow.end", {"workflow": name, "status": "failed"})
            return False
    _log("workflow.end", {"workflow": name, "status": "ok"})
    return True


def undo_last(n: int = 1) -> None:
    for _ in range(min(n, len(_HISTORY))):
        name, step = _HISTORY.pop()
        undo = step.get("undo")
        if callable(undo):
            try:
                undo()
                _log("workflow.undo", {"workflow": name, "step": step.get("name"), "status": "ok"})
            except Exception as e:  # pragma: no cover
                _log(
                    "workflow.undo",
                    {"workflow": name, "step": step.get("name"), "status": "failed", "error": str(e)},
                )


def review_workflow_logs(threshold: int = 3) -> None:
    """Check workflow logs for repeated failures or policy denials."""
    events = notification.list_events(50)
    failures: Dict[str, int] = {}
    for ev in events:
        if ev.get("event") == "workflow.step":
            payload = ev.get("payload", {})
            step = payload.get("step", "")
            status = payload.get("status")
            if status == "failed":
                key = f"failed:{step}"
                failures[key] = failures.get(key, 0) + 1
                if failures[key] >= threshold:
                    save_reflection(
                        parent=ev.get("id", ""),
                        intent={"workflow": payload.get("workflow"), "step": step},
                        result=None,
                        reason=f"Step '{step}' failed repeatedly",
                        next_step="optimize",
                        plugin="workflow",
                    )
                    failures[key] = 0
            elif status == "denied":
                save_reflection(
                    parent=ev.get("id", ""),
                    intent={"workflow": payload.get("workflow"), "step": step},
                    result=None,
                    reason=f"Step '{step}' denied by policy",
                    next_step="edit_workflow",
                    plugin="workflow",
                )


if __name__ == "__main__":  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="Workflow controller")
    parser.add_argument("--load")
    parser.add_argument("--list-workflows", action="store_true")
    parser.add_argument("--run-workflow")
    parser.add_argument("--edit-workflow")
    parser.add_argument("--run")
    parser.add_argument("--undo", type=int, default=0)
    parser.add_argument("--review", action="store_true")
    parser.add_argument("--policy")
    args = parser.parse_args()

    engine = PolicyEngine(args.policy) if args.policy and PolicyEngine else None

    if args.load:
        load_workflows(args.load)
    if args.list_workflows:
        for wf in WORKFLOWS:
            src = WORKFLOW_FILES.get(wf)
            print(f"{wf} -> {src}")
    if args.run_workflow:
        if run_workflow(args.run_workflow, policy_engine=engine):
            print("workflow finished")
        else:
            print("workflow failed")
    if args.edit_workflow:
        path = WORKFLOW_FILES.get(args.edit_workflow)
        if not path:
            print("workflow not found")
        else:
            editor = os.getenv("EDITOR", "nano")
            os.system(f"{editor} {path}")
            load_workflow_file(str(path))
            print("reloaded")

    if args.undo:
        undo_last(args.undo)
    if args.run:
        if run_workflow(args.run, policy_engine=engine):
            print("workflow finished")
        else:
            print("workflow failed")
    if args.review:
        review_workflow_logs()
        print("review complete")


