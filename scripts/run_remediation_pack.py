from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from scripts.run_recovery_task import _run_allowed


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Execute a remediation pack with strict allowlist checks.")
    parser.add_argument("pack_path", help="Path to pack JSON")
    args = parser.parse_args(argv)

    root = Path.cwd().resolve()
    pack_path = (root / args.pack_path).resolve() if not Path(args.pack_path).is_absolute() else Path(args.pack_path)
    payload = json.loads(pack_path.read_text(encoding="utf-8"))

    pack_id = str(payload.get("pack_id") or "unknown")
    steps_payload = payload.get("steps") if isinstance(payload.get("steps"), list) else []
    run_steps: list[dict[str, object]] = []
    overall_ok = True
    for index, raw in enumerate(steps_payload):
        if not isinstance(raw, dict):
            continue
        command = str(raw.get("command") or "")
        allowed, exit_code, stderr = _run_allowed(command, root=root)
        row = {
            "index": index,
            "name": str(raw.get("name") or f"step_{index}"),
            "command": command,
            "allowed": allowed,
            "exit_code": exit_code,
            "status": "ok" if allowed and exit_code == 0 else "failed",
            "stderr": stderr,
        }
        run_steps.append(row)
        if not allowed or exit_code != 0:
            overall_ok = False
            break

    report = {
        "schema_version": 1,
        "generated_at": _iso_now(),
        "pack_id": pack_id,
        "pack_path": str(pack_path.relative_to(root)),
        "status": "completed" if overall_ok else "failed",
        "steps": run_steps,
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = root / "glow/forge/remediation/runs" / f"run_{stamp}_{pack_id}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "report_path": str(report_path.relative_to(root))}, sort_keys=True))
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
