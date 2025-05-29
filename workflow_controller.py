import os
import json
import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Any, Tuple

import notification
from memory_manager import save_reflection

try:
    from policy_engine import PolicyEngine
except Exception:  # pragma: no cover - optional dependency
    PolicyEngine = None  # type: ignore

MEMORY_DIR = Path(os.getenv("MEMORY_DIR", "logs/memory"))
EVENT_PATH = MEMORY_DIR / "events.jsonl"
EVENT_PATH.parent.mkdir(parents=True, exist_ok=True)


def _log(event: str, payload: Dict[str, Any]) -> None:
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "event": event,
        "payload": payload,
    }
    with open(EVENT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    notification.send(event, payload)


Step = Dict[str, Any]
WORKFLOWS: Dict[str, List[Step]] = {}
_HISTORY: List[Tuple[str, Step]] = []


def register_workflow(name: str, steps: List[Step]) -> None:
    """Register a workflow consisting of a list of step mappings."""
    WORKFLOWS[name] = steps


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
                _log("workflow.step", {"workflow": name, "step": step.get("name"), "status": "denied"})
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
    """Check workflow logs for repeated failures and save reflections."""
    events = notification.list_events(50)
    failures: Dict[str, int] = {}
    for ev in events:
        if ev.get("event") == "workflow.step":
            payload = ev.get("payload", {})
            if payload.get("status") == "failed":
                step = payload.get("step", "")
                count = failures.get(step, 0) + 1
                failures[step] = count
                if count >= threshold:
                    save_reflection(
                        parent=ev.get("id", ""),
                        intent={"workflow": payload.get("workflow"), "step": step},
                        result=None,
                        reason=f"Step '{step}' failed repeatedly",
                        next_step="optimize",
                        plugin="workflow",
                    )
                    failures[step] = 0


if __name__ == "__main__":  # pragma: no cover - CLI
    import argparse

    parser = argparse.ArgumentParser(description="Workflow controller")
    parser.add_argument("--run")
    parser.add_argument("--undo", type=int, default=0)
    parser.add_argument("--review", action="store_true")
    parser.add_argument("--policy")
    args = parser.parse_args()

    engine = PolicyEngine(args.policy) if args.policy and PolicyEngine else None

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


