from admin_utils import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
"""Workflow template library utilities and CLI."""

import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml  # type: ignore  # YAML workflow library
except Exception:  # pragma: no cover - optional
    yaml = None

import workflow_controller as wc

LIB_DIR = Path(os.getenv("WORKFLOW_LIBRARY", "workflows"))
LIB_DIR.mkdir(exist_ok=True)


def _apply_params(text: str, params: Dict[str, str]) -> str:
    """Fill ``text`` placeholders using ``params``."""
    try:
        return text.format(**params)
    except Exception:
        return text


def _apply_params_recursive(obj: Any, params: Dict[str, str]) -> Any:
    if isinstance(obj, str):
        return _apply_params(obj, params)
    if isinstance(obj, list):
        return [_apply_params_recursive(o, params) for o in obj]
    if isinstance(obj, dict):
        return {k: _apply_params_recursive(v, params) for k, v in obj.items()}
    return obj


def list_templates() -> List[str]:
    names: List[str] = []
    for ext in ("*.yml", "*.yaml", "*.json", "*.py"):
        for fp in LIB_DIR.glob(ext):
            names.append(fp.stem)
    return sorted(names)


def get_template_path(name: str) -> Optional[Path]:
    for ext in (".yml", ".yaml", ".json", ".py"):
        fp = LIB_DIR / f"{name}{ext}"
        if fp.exists():
            return fp
    return None


def preview_template(name: str) -> str:
    fp = get_template_path(name)
    if not fp:
        raise FileNotFoundError(name)
    return fp.read_text(encoding="utf-8")


def clone_template(name: str, dest: str) -> Path:
    fp = get_template_path(name)
    if not fp:
        raise FileNotFoundError(name)
    dest_path = Path(dest)
    dest_path.write_text(fp.read_text(encoding="utf-8"), encoding="utf-8")
    return dest_path


def suggest_workflow(goal: str) -> Dict[str, Any]:
    """Return a very simple workflow suggestion based on ``goal``."""
    goal_l = goal.lower()
    for name in list_templates():
        if name.replace("_", " ") in goal_l:
            fp = get_template_path(name)
            if fp:
                try:
                    text = fp.read_text(encoding="utf-8")
                    if fp.suffix in {".yml", ".yaml"}:
                        return yaml.safe_load(text) if yaml else wc._load_yaml(text)
                    if fp.suffix == ".json":
                        return json.loads(text)
                except Exception:
                    pass
    return {
        "name": goal_l.replace(" ", "_")[:20],
        "steps": [
            {
                "name": "note",
                "action": "builtins.print",  # placeholder
                "params": {"text": goal},
            }
        ],
    }


def save_template(src: str, name: Optional[str] = None) -> Path:
    src_path = Path(src)
    if not src_path.exists():
        raise FileNotFoundError(src)
    if not name:
        name = src_path.stem
    dest = LIB_DIR / src_path.with_suffix("").name
    dest = dest.with_suffix(src_path.suffix)
    dest.write_text(src_path.read_text(encoding="utf-8"), encoding="utf-8")
    return dest


def load_template(name: str, params: Optional[Dict[str, str]] = None) -> None:
    fp = get_template_path(name)
    if not fp:
        raise FileNotFoundError(name)
    text = fp.read_text(encoding="utf-8")
    tmp = fp.suffix
    if tmp in {".yml", ".yaml"}:
        data = yaml.safe_load(text) if yaml else wc._load_yaml(text)
    elif tmp == ".json":
        data = json.loads(text)
    elif tmp == ".py":
        spec: Dict[str, Any] = {}
        exec(compile(text, str(fp), "exec"), spec)
        data = spec.get("WORKFLOW", spec)
    else:
        raise ValueError("Unsupported workflow file")
    if params:
        data = _apply_params_recursive(data, params)
    steps = []
    for st in data.get("steps", []):
        step = dict(st)
        act = step.get("action")
        if isinstance(act, str):
            step["action"] = wc._wrap_action(act, step.get("params"))
        undo = step.get("undo")
        if isinstance(undo, str):
            step["undo"] = wc._wrap_action(undo, step.get("undo_params"))
        of = step.get("on_fail")
        if isinstance(of, str):
            step["on_fail"] = [wc._wrap_action(of)]
        elif isinstance(of, list):
            step["on_fail"] = [wc._wrap_action(o) if isinstance(o, str) else o for o in of]
        steps.append(step)
    wc.register_workflow(data.get("name", name), steps)
    wc.WORKFLOW_FILES[data.get("name", name)] = fp


def main() -> None:  # pragma: no cover - CLI
    import argparse

    ap = argparse.ArgumentParser(prog="workflow_lib")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("list")

    p = sub.add_parser("preview")
    p.add_argument("name")

    c = sub.add_parser("clone")
    c.add_argument("name")
    c.add_argument("dest")

    s = sub.add_parser("save")
    s.add_argument("src")
    s.add_argument("name", nargs="?")

    l = sub.add_parser("load")
    l.add_argument("name")
    l.add_argument("--params")

    args = ap.parse_args()

    if args.cmd == "list":
        for n in list_templates():
            print(n)
    elif args.cmd == "preview":
        print(preview_template(args.name))
    elif args.cmd == "clone":
        out = clone_template(args.name, args.dest)
        print(out)
    elif args.cmd == "save":
        dest = save_template(args.src, args.name)
        print(dest)
    elif args.cmd == "load":
        params = json.loads(args.params or "{}") if args.params else {}
        load_template(args.name, params=params)
        print(f"Loaded {args.name}")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
