from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sentientos.signed_strategic import sign_object, strategic_signing_enabled


def _read_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Sign unsigned strategic proposals/changes")
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()

    if os.getenv("SENTIENTOS_STRATEGIC_SIGN_EXISTING", "0") != "1":
        print(json.dumps({"tool": "sign_strategic", "status": "blocked", "reason": "set SENTIENTOS_STRATEGIC_SIGN_EXISTING=1"}, indent=2, sort_keys=True))
        return 0
    if not strategic_signing_enabled():
        print(json.dumps({"tool": "sign_strategic", "status": "skipped", "reason": "signing_disabled"}, indent=2, sort_keys=True))
        return 0

    root = Path(args.repo_root).resolve()
    signed = 0
    for kind, pattern in (("proposal", "glow/forge/strategic/proposals/proposal_*.json"), ("change", "glow/forge/strategic/changes/change_*.json")):
        for path in sorted(root.glob(pattern), key=lambda item: item.name):
            payload = _read_json(path)
            marker = payload.get("strategic_signature") if isinstance(payload.get("strategic_signature"), dict) else {}
            if isinstance(marker.get("path"), str):
                continue
            object_id = str(payload.get("proposal_id") if kind == "proposal" else payload.get("change_id") or path.stem)
            created_at = str(payload.get("created_at") or payload.get("applied_at") or "")
            rel = str(path.relative_to(root))
            sign_object(root, kind=kind, object_id=object_id, object_rel_path=rel, object_payload=payload, created_at=created_at or None)
            signed += 1
    print(json.dumps({"tool": "sign_strategic", "status": "ok", "signed_count": signed}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
