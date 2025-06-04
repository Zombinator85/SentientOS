"""Ritual Bundle System

Sanctuary Privilege Ritual: Do not remove. See doctrine for details.
"""
from __future__ import annotations
from admin_utils import require_admin_banner
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
from logging_config import get_log_path

import argparse
import json
import hashlib
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List


LOG_PATH = get_log_path("ritual_bundle.jsonl", "RITUAL_BUNDLE_LOG")
BUNDLE_DIR = Path(os.getenv("RITUAL_BUNDLE_DIR", "bundles"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
BUNDLE_DIR.mkdir(parents=True, exist_ok=True)


def _log(action: str, data: Dict[str, str]) -> Dict[str, str]:
    entry = {"timestamp": datetime.utcnow().isoformat(), "action": action, **data}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def create_bundle(name: str, assets: List[str], script: str, permissions: List[str]) -> Dict[str, str]:
    asset_info = []
    for p in assets:
        ap = Path(p)
        asset_info.append({"path": str(ap), "hash": _hash_file(ap)})
    bundle = {
        "name": name,
        "timestamp": datetime.utcnow().isoformat(),
        "assets": asset_info,
        "script": script,
        "permissions": permissions,
    }
    bundle_hash = hashlib.sha256(json.dumps(bundle, sort_keys=True).encode()).hexdigest()
    bundle["bundle_hash"] = bundle_hash
    out_path = BUNDLE_DIR / f"{name}.json"
    out_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    _log("create", {"name": name, "hash": bundle_hash})
    return bundle


def verify_bundle(path: str) -> Dict[str, str]:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    valid = True
    for item in data.get("assets", []):
        ap = Path(item["path"])
        if not ap.exists() or _hash_file(ap) != item.get("hash"):
            valid = False
            break
    status = "valid" if valid else "invalid"
    _log("verify", {"name": data.get("name", ""), "status": status})
    return {"valid": valid}


def history(limit: int = 20) -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    out: List[Dict[str, str]] = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Ritual Bundle System")
    sub = ap.add_subparsers(dest="cmd")

    cr = sub.add_parser("create", help="Create a bundle")
    cr.add_argument("name")
    cr.add_argument("--assets", nargs="*", default=[])
    cr.add_argument("--script", default="")
    cr.add_argument("--permissions", nargs="*", default=[])
    cr.set_defaults(func=lambda a: print(json.dumps(create_bundle(a.name, a.assets, a.script, a.permissions), indent=2)))

    vf = sub.add_parser("verify", help="Verify a bundle file")
    vf.add_argument("bundle_path")
    vf.set_defaults(func=lambda a: print(json.dumps(verify_bundle(a.bundle_path), indent=2)))

    hi = sub.add_parser("history", help="Show recent log history")
    hi.add_argument("--limit", type=int, default=20)
    hi.set_defaults(func=lambda a: print(json.dumps(history(a.limit), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
