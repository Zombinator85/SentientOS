"""Simple CLI editor for workflow files."""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    yaml = None

from workflow_controller import _load_yaml


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


def edit_loop(path: Path, policy: str | None = None) -> None:
    data = load_file(path)
    steps: List[Dict[str, Any]] = data.get("steps", [])
    while True:
        print("\nWorkflow:", data.get("name", path.stem))
        for i, st in enumerate(steps):
            print(f"{i+1}. {st.get('name')}")
        print("a:Add step d:Delete step r:Reorder s:Save q:Quit")
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
        elif choice == "s":
            data["steps"] = steps
            save_file(path, data)
            print("saved")
        elif choice == "q":
            break


def main() -> None:  # pragma: no cover - CLI
    ap = argparse.ArgumentParser(description="Workflow editor")
    ap.add_argument("path")
    ap.add_argument("--policy")
    args = ap.parse_args()
    edit_loop(Path(args.path), policy=args.policy)


if __name__ == "__main__":
    main()
