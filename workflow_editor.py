"""CLI entry enforcing Sanctuary Privilege Ritual."""
"""Simple CLI editor for workflow files."""

import argparse
import json
import datetime
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple
from sentient_banner import print_banner, print_closing, ENTRY_BANNER
from admin_utils import require_admin_banner

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    yaml = None

from workflow_controller import _load_yaml

AID_LOG = Path(os.getenv("WORKFLOW_AUDIT", "logs/workflow_audit.jsonl"))
AID_LOG.parent.mkdir(parents=True, exist_ok=True)


def _log(action: str, info: Dict[str, Any]) -> None:
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "action": action,
        "info": info,
    }
    with open(AID_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def load_file(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix in {".yml", ".yaml"}:
        data = yaml.safe_load(text) if yaml else _load_yaml(text)
    else:
        data = json.loads(text)
    if "steps" not in data:
        data["steps"] = []
    return data


def save_file(path: Path, data: Dict[str, Any]) -> None:
    if path.suffix in {".yml", ".yaml"} and yaml:
        text = yaml.safe_dump(data)
        yaml.safe_load(text)
    else:
        text = json.dumps(data, indent=2)
        json.loads(text)
    path.write_text(text, encoding="utf-8")


def ai_suggest_edits(data: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    steps = data.get("steps", [])
    explanation = []
    names = set()
    for st in steps:
        name = st.get("name")
        if name in names:
            new_name = f"{name}_1"
            st["name"] = new_name
            explanation.append(f"Renamed duplicate step '{name}' -> '{new_name}'")
        names.add(st.get("name"))
    sorted_steps = sorted(steps, key=lambda s: s.get("name", ""))
    if sorted_steps != steps:
        data["steps"] = sorted_steps
        explanation.append("Reordered steps alphabetically")
    if len(steps) > 8:
        explanation.append("Consider splitting long workflow")
    return data, "; ".join(explanation) or "No changes"


def edit_loop(path: Path, policy: str | None = None) -> None:
    data = load_file(path)
    steps: List[Dict[str, Any]] = data.get("steps", [])
    while True:
        print("\nWorkflow:", data.get("name", path.stem))
        for i, st in enumerate(steps):
            print(f"{i+1}. {st.get('name')}")
        print("a:Add step d:Delete step r:Reorder m:AI edit s:Save q:Quit")
        choice = input("> ").strip().lower()
        if choice == "a":
            name = input("step name: ")
            action = input("action (module.fn): ")
            steps.append({"name": name, "action": action})
        elif choice == "d":
            idx = int(input("index: ") or "0") - 1
            if 0 <= idx < len(steps):
                steps.pop(idx)
        elif choice == "r":
            idx = int(input("index: ") or "0") - 1
            new = int(input("new position: ") or "0") - 1
            if 0 <= idx < len(steps) and 0 <= new < len(steps):
                st = steps.pop(idx)
                steps.insert(new, st)
        elif choice == "m":
            new_data, expl = ai_suggest_edits({"steps": steps, "name": data.get("name")})
            if expl:
                print("AI Suggestion:", expl)
            if input("apply? [y/N] ").lower().startswith("y"):
                steps = new_data.get("steps", steps)
                _log("ai_edit_accept", {"path": str(path), "explanation": expl})
            else:
                _log("ai_edit_dismiss", {"path": str(path), "explanation": expl})
        elif choice == "s":
            data["steps"] = steps
            save_file(path, data)
            print("saved")
        elif choice == "q":
            _log("quit", {"path": str(path)})
            break


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
    ap = argparse.ArgumentParser(description=ENTRY_BANNER)
    ap.add_argument("path")
    ap.add_argument("--policy")
    args = ap.parse_args()
    print_banner()
    edit_loop(Path(args.path), policy=args.policy)
    print_closing()


if __name__ == "__main__":
    main()
