"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Workflow template library utilities and CLI."""

import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml  # type: ignore[import-untyped]  # YAML workflow library
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
    for ext in ("*.yml", "*.yaml", "*.json"):
        for fp in LIB_DIR.glob(ext):
            names.append(fp.stem)
    return sorted(names)


def get_template_path(name: str) -> Optional[Path]:
    for ext in (".yml", ".yaml", ".json"):
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
    """Reject the retired template-to-execution bridge."""

    fp = get_template_path(name)
    if not fp:
        raise FileNotFoundError(name)
    wc.load_workflow_file(str(fp))


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
