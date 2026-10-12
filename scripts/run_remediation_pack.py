from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from scripts.run_recovery_task import _run_allowed
from sentientos.artifact_catalog import append_catalog_entry
from sentientos.private_file_custody import PrivateFileCustodyError, publish_immutable_bytes
from sentientos.remediation_pack import (
    MAX_REMEDIATION_PACK_BYTES,
    MAX_REMEDIATION_RUN_BYTES,
    _PACK_ID_RE,
    _read_bounded_file,
    _strict_json_object,
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def execute_pack_file(pack_path: Path, *, root: Path) -> dict[str, object]:
    root = root.resolve()
    pack_path = pack_path.resolve(strict=True)
    try:
        pack_relative_path = pack_path.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError("remediation_pack_outside_root") from exc
    pack_bytes = _read_bounded_file(pack_path, max_bytes=MAX_REMEDIATION_PACK_BYTES)
    payload = _strict_json_object(pack_bytes)

    pack_id_value = payload.get("pack_id")
    if not isinstance(pack_id_value, str) or not _PACK_ID_RE.fullmatch(pack_id_value):
        raise ValueError("remediation_pack_id_invalid")
    pack_id = pack_id_value
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

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"run_{stamp}_{pack_id}"
    report = {
        "schema_version": 1,
        "run_id": run_id,
        "generated_at": _iso_now(),
        "pack_id": pack_id,
        "pack_path": pack_relative_path,
        "pack_sha256": hashlib.sha256(pack_bytes).hexdigest(),
        "incident_id": payload.get("incident_id"),
        "status": "completed" if overall_ok else "failed",
        "steps": run_steps,
    }
    report_path = root / "glow/forge/remediation/runs" / f"run_{stamp}_{pack_id}.json"
    encoded = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(encoded) > MAX_REMEDIATION_RUN_BYTES:
        raise ValueError("remediation_run_report_too_large")
    if os.name == "posix":
        publish_immutable_bytes(report_path, encoded, max_bytes=MAX_REMEDIATION_RUN_BYTES,
            collision_code="remediation_run_identity_conflict")
    else:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with report_path.open("xb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError as exc:
            raise PrivateFileCustodyError("remediation_run_identity_conflict") from exc
    report["report_path"] = str(report_path.relative_to(root))
    append_catalog_entry(
        root,
        kind="remediation_run",
        artifact_id=run_id,
        relative_path=report["report_path"],
        schema_name="remediation_run",
        schema_version=1,
        links={"run_id": run_id, "pack_id": pack_id, "incident_id": payload.get("incident_id")},
        summary={"status": report["status"]},
        ts=str(report.get("generated_at") or _iso_now()),
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Execute a remediation pack with strict allowlist checks.")
    parser.add_argument("pack_path", help="Path to pack JSON")
    args = parser.parse_args(argv)

    root = Path.cwd().resolve()
    pack_path = (root / args.pack_path).resolve() if not Path(args.pack_path).is_absolute() else Path(args.pack_path)
    report = execute_pack_file(pack_path, root=root)
    print(json.dumps({"status": report["status"], "report_path": report.get("report_path")}, sort_keys=True))
    return 0 if str(report.get("status")) == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
