"""Create a portable, digest-bound snapshot of a campaign's initial history.

The snapshot contains the complete record and receipt bytes in base64. It is
created only when explicitly requested because it copies private developmental
history into the selected output location.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any, Mapping

from sentientos.local_model_authority import digest_payload
from work.rootless_history_boundary_campaign import _history_boundary, _load_plan


def _bundle_semantic(bundle: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in bundle.items() if key != "bundle_digest"}


def _read_existing(path: Path) -> tuple[dict[str, Any], bytes]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("history_seed_bundle_existing_file_invalid")
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("history_seed_bundle_existing_payload_invalid")
    canonical_forms = (
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
            + b"\n",
        json.dumps(value, sort_keys=True, indent=2).encode("utf-8") + b"\n")
    if raw not in canonical_forms:
        raise ValueError("history_seed_bundle_existing_payload_noncanonical")
    if value.get("bundle_digest") != digest_payload(_bundle_semantic(value)):
        raise ValueError("history_seed_bundle_existing_digest_invalid")
    return value, raw


def create_bundle(*, plan_path: Path, history_root: Path) -> dict[str, Any]:
    plan = _load_plan(plan_path)
    before = _history_boundary(history_root)
    expected = plan.get("initial_history_boundary")
    if (not isinstance(expected, Mapping)
            or before.get("boundary_digest") != expected.get("boundary_digest")
            or before != dict(expected)):
        raise ValueError("history_seed_bundle_plan_boundary_mismatch")
    root = history_root.resolve(strict=True)
    file_payloads: list[dict[str, Any]] = []
    for row in before["files"]:
        relative_path = row["path"]
        path = root / Path(relative_path)
        if path.is_symlink() or not path.is_file():
            raise ValueError("history_seed_bundle_source_file_invalid")
        raw = path.read_bytes()
        if (len(raw) > 1_048_576
                or len(raw) != row["size_bytes"]
                or hashlib.sha256(raw).hexdigest() != row["sha256"]):
            raise ValueError("history_seed_bundle_source_file_changed")
        file_payloads.append({**row,
            "content_base64": base64.b64encode(raw).decode("ascii")})
    after = _history_boundary(root)
    if after != before:
        raise ValueError("history_seed_bundle_source_boundary_changed")
    semantic = {
        "schema_version": "sentientos.rootless_history_campaign_seed_bundle:v1",
        "campaign_id": plan["campaign_id"],
        "plan_digest": plan["plan_digest"],
        "task_family_id": plan["task_family_id"],
        "source_history_boundary_digest": before["boundary_digest"],
        "source_history_file_count": len(file_payloads),
        "source_history_total_size_bytes": before["total_size_bytes"],
        "source_snapshot_atomic": False,
        "files": file_payloads,
    }
    return {**semantic, "bundle_digest": digest_payload(semantic)}


def persist_or_verify(bundle: Mapping[str, Any], output_path: Path, *,
        verify_existing: bool) -> str:
    output = output_path.expanduser().absolute()
    if (output.parent.is_symlink() or not output.parent.is_dir()
            or output.parent.resolve(strict=True) != output.parent):
        raise ValueError("history_seed_bundle_output_parent_invalid")
    if os.name == "nt":
        from sentientos.windows_handle_custody import (
            WindowsHandleCustodyError, verify_explicit_directory)
        try:
            verify_explicit_directory(output.parent, require_private_acl=True)
        except (WindowsHandleCustodyError, OSError) as exc:
            raise ValueError("history_seed_bundle_output_parent_not_private") from exc
    elif stat.S_IMODE(output.parent.stat().st_mode) & 0o077:
        raise ValueError("history_seed_bundle_output_parent_not_private")
    if verify_existing:
        existing, raw = _read_existing(output)
        expected = (json.dumps(dict(bundle), sort_keys=True, indent=2) + "\n").encode("utf-8")
        if existing != dict(bundle) or raw not in {
                expected,
                (json.dumps(dict(bundle), sort_keys=True,
                    separators=(",", ":")) + "\n").encode("utf-8")}:
            raise ValueError("history_seed_bundle_existing_mismatch")
        return "verified_existing"
    if output.exists() or output.is_symlink():
        raise ValueError("history_seed_bundle_output_already_exists")
    raw = (json.dumps(dict(bundle), sort_keys=True, indent=2) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(output, flags, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    return "created"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--history-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--verify-existing", action="store_true")
    args = parser.parse_args()
    history_root = args.history_root.expanduser().resolve(strict=True)
    output_path = args.output.expanduser().absolute()
    if output_path == history_root or history_root in output_path.parents:
        raise ValueError("history_seed_bundle_output_inside_source_history")
    bundle = create_bundle(plan_path=args.plan, history_root=args.history_root)
    status = persist_or_verify(bundle, args.output,
        verify_existing=args.verify_existing)
    print(json.dumps({"status": status, "campaign_id": bundle["campaign_id"],
        "plan_digest": bundle["plan_digest"],
        "source_history_boundary_digest": bundle[
            "source_history_boundary_digest"],
        "source_history_file_count": bundle["source_history_file_count"],
        "source_history_total_size_bytes": bundle[
            "source_history_total_size_bytes"],
        "bundle_digest": bundle["bundle_digest"],
        "private_history_copied": True,
        "model_inference_performed": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
