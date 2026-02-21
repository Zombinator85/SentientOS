from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from sentientos.recovery_allowlist import ALLOWED_COMMANDS, normalize_command
from sentientos.recovery_tasks import append_task_record, list_tasks


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _open_task(rows: list[dict[str, object]], kind: str | None) -> dict[str, object] | None:
    done_kinds = {str(row.get("kind")) for row in rows if str(row.get("status")) == "done"}
    for row in rows:
        row_kind = str(row.get("kind", ""))
        status = str(row.get("status", "open"))
        if not row_kind or status == "done" or row_kind in done_kinds:
            continue
        if kind is not None and row_kind != kind:
            continue
        return row
    return None


def _run_allowed(command: str, *, root: Path) -> tuple[bool, int, str]:
    normalized = normalize_command(command)
    if normalized not in ALLOWED_COMMANDS:
        return False, 126, f"command_not_allowed:{' '.join(normalized)}"
    completed = subprocess.run(list(normalized), cwd=root, check=False, capture_output=True, text=True)
    stderr = (completed.stderr or completed.stdout or "").strip()
    return True, completed.returncode, stderr[:400]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Execute one queued recovery task with command allow-listing.")
    parser.add_argument("--kind", help="Run a specific open task kind", default=None)
    args = parser.parse_args(argv)

    root = Path.cwd().resolve()
    rows = list_tasks(root)
    task = _open_task(rows, args.kind)
    if task is None:
        print(json.dumps({"status": "noop", "reason": "no_open_task"}, sort_keys=True))
        return 0

    commands: list[str] = []
    raw = task.get("suggested_command")
    if isinstance(raw, str) and raw.strip():
        commands.append(raw.strip())
    follow = task.get("suggested_followup_command")
    if isinstance(follow, str) and follow.strip():
        commands.append(follow.strip())

    overall_ok = True
    steps: list[dict[str, object]] = []
    for command in commands:
        allowed, exit_code, stderr = _run_allowed(command, root=root)
        step = {
            "command": command,
            "allowed": allowed,
            "exit_code": exit_code,
            "status": "ok" if allowed and exit_code == 0 else "failed",
            "stderr": stderr,
        }
        steps.append(step)
        if not allowed or exit_code != 0:
            overall_ok = False
            break

    done_record = {
        "kind": str(task.get("kind", "unknown")),
        "status": "done",
        "done_at": _iso_now(),
        "result": "ok" if overall_ok else "failed",
        "run_steps": steps,
    }
    append_task_record(root, done_record)

    report = {
        "schema_version": 1,
        "generated_at": _iso_now(),
        "task": task,
        "result": done_record,
    }
    out_dir = root / "glow/forge/recovery_runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = out_dir / f"recovery_{stamp}.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps({"status": done_record["result"], "kind": done_record["kind"], "report_path": str(report_path.relative_to(root))}, sort_keys=True))
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
