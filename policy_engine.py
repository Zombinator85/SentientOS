from __future__ import annotations

from admin_utils import require_admin_banner
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
# Modular policy, gesture, and persona engine.

import json
import time
import re
from pathlib import Path
from typing import Any, Dict, List

import final_approval

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    yaml = None


def _load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"policies": [], "personas": {}}
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except Exception:
        if yaml is None:
            raise
        data = yaml.safe_load(text)
    if isinstance(data, list):
        return {"policies": data, "personas": {}}
    return data


class PolicyEngine:
    """Load and evaluate gesture/persona policies."""

    def __init__(self, config_path: str) -> None:
        self.path = Path(config_path)
        self.policies: List[Dict[str, Any]] = []
        self.personas: Dict[str, Dict[str, Any]] = {}
        self.logs: List[Dict[str, Any]] = []
        self.history: List[Dict[str, Any]] = []
        self.load()

    def load(self) -> None:
        data = _load_config(self.path)
        self.personas = data.get("personas", {})
        self.policies = data.get("policies", [])
        self.history.append({"timestamp": time.time(), "data": data})

    def reload(self) -> None:
        self.load()

    def apply_policy(self, path: str, approvers: Optional[List[str]] = None) -> None:
        """Replace active policy set with ``path`` contents."""
        kwargs = {"approvers": approvers} if approvers is not None else {}
        if not final_approval.request_approval(f"policy {path}", **kwargs):
            return
        new_data = _load_config(Path(path))
        self.history.append({"timestamp": time.time(), "data": new_data})
        self.personas = new_data.get("personas", {})
        self.policies = new_data.get("policies", [])

    def rollback(self) -> bool:
        if len(self.history) < 2:
            return False
        self.history.pop()
        data = self.history[-1]["data"]
        self.personas = data.get("personas", {})
        self.policies = data.get("policies", [])
        return True

    # -- Evaluation ---------------------------------------------------------
    def evaluate(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Evaluate an event and return actions triggered."""
        actions: List[Dict[str, Any]] = []
        for pol in self.policies:
            if self._match(pol.get("conditions", {}), event):
                actions.extend(pol.get("actions", []))
        if actions:
            self._log(event, actions)
        return actions

    def _match(self, cond: Dict[str, Any], event: Dict[str, Any]) -> bool:
        emotions = cond.get("emotions", {})
        for k, v in emotions.items():
            if event.get("emotions", {}).get(k, 0) < float(v):
                return False
        ev_name = cond.get("event")
        if ev_name and ev_name != event.get("event"):
            return False
        persona = cond.get("persona")
        if persona and persona != event.get("persona"):
            return False
        tags = cond.get("tags")
        if tags:
            ev_tags = event.get("tags", [])
            if not any(t in ev_tags for t in tags):
                return False
        return True

    def _log(self, event: Dict[str, Any], actions: List[Dict[str, Any]]) -> None:
        self.logs.append({
            "timestamp": time.time(),
            "event": event,
            "actions": actions,
        })


# -- CLI ----------------------------------------------------------------------

def _diff(a: Dict[str, Any], b_text: str) -> str:
    import difflib
    a_text = json.dumps(a, indent=2, sort_keys=True)
    diff = difflib.unified_diff(a_text.splitlines(), b_text.splitlines())
    return "\n".join(diff)


def main() -> None:  # pragma: no cover - CLI usage
    import argparse

    parser = argparse.ArgumentParser(description="Policy/Persona manager")
    parser.add_argument(
        "--final-approvers",
        default=os.getenv("REQUIRED_FINAL_APPROVER", "4o"),
        help="Comma or space separated list of required approvers",
    )
    parser.add_argument(
        "--final-approver-file",
        help="File with approver names (JSON list or newline separated)",
    )
    parser.add_argument("--config", default="config/policies.yml")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("policy", help="Policy operations")
    p_sub = p.add_subparsers(dest="action")
    p_sub.add_parser("show", help="Show active policies")
    d = p_sub.add_parser("diff", help="Diff against file")
    d.add_argument("file")
    a = p_sub.add_parser("apply", help="Apply policy file")
    a.add_argument("file")
    p_sub.add_parser("rollback", help="Rollback to previous policy")

    persona = sub.add_parser("persona", help="Swap persona")
    persona.add_argument("name")

    gesture = sub.add_parser("gesture", help="Trigger gesture")
    gesture.add_argument("name")

    args = parser.parse_args()
    if args.final_approver_file:
        fp = Path(args.final_approver_file)
        chain = final_approval.load_file_approvers(fp) if fp.exists() else []
        final_approval.override_approvers(chain, source="file")
    elif args.final_approvers:
        fp = Path(args.final_approvers)
        if fp.exists():
            chain = final_approval.load_file_approvers(fp)
        else:
            parts = re.split(r"[,\s]+", args.final_approvers)
            chain = [a.strip() for a in parts if a.strip()]
        final_approval.override_approvers(chain, source="cli")
    engine = PolicyEngine(args.config)

    if args.cmd == "policy":
        if args.action == "show":
            print(json.dumps({"personas": engine.personas, "policies": engine.policies}, indent=2))
        elif args.action == "diff":
            other_text = Path(args.file).read_text(encoding="utf-8")
            print(_diff({"personas": engine.personas, "policies": engine.policies}, other_text))
        elif args.action == "apply":
            engine.apply_policy(args.file, approvers=final_approval.load_approvers())
            print("applied")
        elif args.action == "rollback":
            if engine.rollback():
                print("rolled back")
            else:
                print("no previous version")
    elif args.cmd == "persona":
        actions = engine.evaluate({"tags": ["persona_swap"], "persona": args.name})
        print(json.dumps(actions, indent=2))
    elif args.cmd == "gesture":
        actions = engine.evaluate({"tags": [args.name]})
        print(json.dumps(actions, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":  # pragma: no cover
    main()
