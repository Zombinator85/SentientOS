from __future__ import annotations

import json
from pathlib import Path

from sentientos.integrity_quarantine import load_state


def _latest_incident(repo_root: Path) -> dict[str, object]:
    paths = sorted((repo_root / "glow/forge/incidents").glob("incident_*.json"), key=lambda item: item.name)
    if not paths:
        return {}
    try:
        payload = json.loads(paths[-1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def main() -> int:
    root = Path.cwd().resolve()
    state = load_state(root).to_dict()
    latest = _latest_incident(root)
    print(json.dumps({"quarantine": state, "latest_incident": latest}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
