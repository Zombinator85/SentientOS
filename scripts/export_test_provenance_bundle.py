from __future__ import annotations

import argparse
import json
import os
import tarfile
import tempfile
import hashlib
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any
import gzip

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.analyze_test_provenance import Thresholds, _load_json, _parse_timestamp, analyze
from scripts.provenance_hash_chain import HASH_ALGO, compute_provenance_hash

DEFAULT_PROVENANCE_DIR = Path("glow/test_runs/provenance")
DEFAULT_BUNDLE_DIR = Path("glow/test_runs/bundles")
DEFAULT_TREND_REPORT = Path("glow/test_runs/test_trend_report.json")
DEFAULT_ARCHIVE_INDEX = Path("glow/test_runs/archive_index.jsonl")


@dataclass(frozen=True)
class SnapshotRecord:
    path: Path
    payload: dict[str, Any]


@dataclass(frozen=True)
class BundleWindow:
    snapshots: list[SnapshotRecord]
    started_at: str
    ended_at: str


def _iso_timestamp(value: datetime) -> str:
    return value.astimezone().isoformat(timespec="seconds")


def _parse_iso_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed


def _load_snapshots(provenance_dir: Path) -> list[SnapshotRecord]:
    records: list[SnapshotRecord] = []
    for path in sorted(candidate for candidate in provenance_dir.glob("*.json") if candidate.is_file()):
        payload = _load_json(path)
        if payload is None:
            continue
        payload["_source"] = str(path)
        records.append(SnapshotRecord(path=path, payload=payload))
    return sorted(records, key=lambda record: (_parse_timestamp(record.payload.get("timestamp")), record.path.name))


def _select_window(
    records: list[SnapshotRecord],
    *,
    last: int,
    from_timestamp: datetime | None,
    to_timestamp: datetime | None,
) -> BundleWindow:
    if from_timestamp or to_timestamp:
        selected = [
            record
            for record in records
            if (from_timestamp is None or _parse_timestamp(record.payload.get("timestamp")) >= from_timestamp)
            and (to_timestamp is None or _parse_timestamp(record.payload.get("timestamp")) <= to_timestamp)
        ]
    else:
        selected = records[-last:]

    if not selected:
        raise ValueError("no provenance snapshots selected for bundle window")

    started_at = str(selected[0].payload.get("timestamp") or selected[0].path.name)
    ended_at = str(selected[-1].payload.get("timestamp") or selected[-1].path.name)
    return BundleWindow(snapshots=selected, started_at=started_at, ended_at=ended_at)


def _verify_selected_chain(window: BundleWindow) -> tuple[bool, list[str], str | None]:
    issues: list[str] = []
    prior_hash: str | None = None
    anchor_prev_hash: str | None = None

    for index, record in enumerate(window.snapshots):
        payload = record.payload
        prev_hash = payload.get("prev_provenance_hash")
        actual_hash = payload.get("provenance_hash")
        hash_algo = payload.get("hash_algo")

        if hash_algo != HASH_ALGO:
            issues.append(f"{record.path.name}: bad hash_algo")
        if not isinstance(prev_hash, str):
            issues.append(f"{record.path.name}: missing prev_provenance_hash")
        if not isinstance(actual_hash, str):
            issues.append(f"{record.path.name}: missing provenance_hash")
            continue

        if index == 0:
            anchor_prev_hash = prev_hash if isinstance(prev_hash, str) else None
        elif prev_hash != prior_hash:
            issues.append(f"{record.path.name}: chain discontinuity (prev_provenance_hash mismatch)")

        payload_for_hash = dict(payload)
        payload_for_hash.pop("_source", None)
        expected_hash = compute_provenance_hash(payload_for_hash, prev_hash if isinstance(prev_hash, str) else None)
        if expected_hash != actual_hash:
            issues.append(f"{record.path.name}: provenance_hash mismatch")

        prior_hash = actual_hash

    return (len(issues) == 0, issues, anchor_prev_hash)


def _default_bundle_name(window: BundleWindow, git_sha: str, fmt: str) -> str:
    start = window.started_at.replace(":", "-")
    end = window.ended_at.replace(":", "-")
    extension = "tar.gz" if fmt == "tar.gz" else "zip"
    return f"provenance_bundle_{start}_{end}_{git_sha}.{extension}"


def _git_sha() -> str:
    env_sha = os.getenv("GITHUB_SHA")
    if env_sha:
        return env_sha[:12]
    head_path = REPO_ROOT / ".git" / "HEAD"
    try:
        head_contents = head_path.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"
    if head_contents.startswith("ref:"):
        ref_path = REPO_ROOT / ".git" / head_contents.split(" ", 1)[1]
        try:
            return ref_path.read_text(encoding="utf-8").strip()[:12]
        except OSError:
            return "unknown"
    return head_contents[:12] or "unknown"


def _write_manifest(
    *,
    window: BundleWindow,
    trend_report_name: str,
    manifest_path: Path,
    anchor_prev_hash: str | None,
) -> dict[str, Any]:
    file_entries = [
        {
            "name": f"provenance/{record.path.name}",
            "provenance_hash": str(record.payload.get("provenance_hash", "")),
        }
        for record in window.snapshots
    ]

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "created_at": _iso_timestamp(datetime.now().astimezone()),
        "repo_root": str(REPO_ROOT),
        "bundle_window": {
            "from": window.started_at,
            "to": window.ended_at,
            "count": len(window.snapshots),
        },
        "hash_algo": HASH_ALGO,
        "first_provenance_hash": str(window.snapshots[0].payload.get("provenance_hash", "")),
        "last_provenance_hash": str(window.snapshots[-1].payload.get("provenance_hash", "")),
        "files": file_entries,
        "trend_report": trend_report_name,
        "windowed": True,
    }
    if anchor_prev_hash is not None:
        manifest["anchor_prev_provenance_hash"] = anchor_prev_hash

    manifest_path.write_text(f"{json.dumps(manifest, indent=2, sort_keys=True)}\n", encoding="utf-8")
    return manifest


def _append_archive_index_entry(index_path: Path, entry: dict[str, Any]) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with index_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{json.dumps(entry, sort_keys=True)}\n")
        handle.flush()
        os.fsync(handle.fileno())


def _regenerate_trend_report(window: BundleWindow, target: Path) -> None:
    runs: list[dict[str, Any]] = []
    for record in window.snapshots:
        payload = dict(record.payload)
        payload["_source"] = record.path.name
        runs.append(payload)
    report = analyze(
        runs,
        Thresholds(
            window_size=min(20, len(runs)) or 1,
            skip_delta=0.15,
            xfail_delta=0.10,
            executed_drop=0.50,
            passed_drop=0.50,
            exceptional_cluster=3,
        ),
        verify_chain_enabled=True,
    )
    target.write_text(f"{json.dumps(report, indent=2, sort_keys=True)}\n", encoding="utf-8")


def _create_deterministic_tar_gz(bundle_root: Path, output_path: Path) -> None:
    with BytesIO() as tar_bytes:
        with tarfile.open(fileobj=tar_bytes, mode="w") as tar:
            for file_path in sorted(path for path in bundle_root.rglob("*") if path.is_file()):
                arcname = file_path.relative_to(bundle_root)
                info = tar.gettarinfo(str(file_path), arcname=str(arcname))
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                info.mtime = 0
                with file_path.open("rb") as source:
                    tar.addfile(info, source)
        tar_payload = tar_bytes.getvalue()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
            gz.write(tar_payload)


def _copy_bundle_inputs(bundle_root: Path, window: BundleWindow, trend_report_path: Path) -> None:
    provenance_root = bundle_root / "provenance"
    provenance_root.mkdir(parents=True, exist_ok=True)
    for record in window.snapshots:
        destination = provenance_root / record.path.name
        destination.write_text(record.path.read_text(encoding="utf-8"), encoding="utf-8")
    destination_report = bundle_root / DEFAULT_TREND_REPORT.name
    destination_report.write_text(trend_report_path.read_text(encoding="utf-8"), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export deterministic provenance bundle from test run snapshots.")
    parser.add_argument("--dir", type=Path, default=DEFAULT_PROVENANCE_DIR, help="Provenance snapshot directory.")
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_BUNDLE_DIR,
        help="Output bundle path or output directory for auto-generated bundle filename.",
    )
    parser.add_argument("--last", type=int, default=50, help="Export most recent N snapshots.")
    parser.add_argument("--from", dest="from_timestamp", type=str, help="ISO-8601 timestamp lower bound (inclusive).")
    parser.add_argument("--to", dest="to_timestamp", type=str, help="ISO-8601 timestamp upper bound (inclusive).")
    parser.add_argument("--format", choices=["tar.gz"], default="tar.gz", help="Bundle archive format.")
    parser.add_argument("--archive-index", type=Path, default=DEFAULT_ARCHIVE_INDEX, help="Append-only bundle archive index path.")
    args = parser.parse_args(argv)

    if args.last <= 0:
        raise ValueError("--last must be > 0")
    if (args.from_timestamp and not args.to_timestamp) or (args.to_timestamp and not args.from_timestamp):
        raise ValueError("--from and --to must be provided together")

    from_timestamp = _parse_iso_timestamp(args.from_timestamp) if args.from_timestamp else None
    to_timestamp = _parse_iso_timestamp(args.to_timestamp) if args.to_timestamp else None

    records = _load_snapshots(args.dir)
    window = _select_window(
        records,
        last=args.last,
        from_timestamp=from_timestamp,
        to_timestamp=to_timestamp,
    )
    chain_ok, issues, anchor_prev_hash = _verify_selected_chain(window)
    if not chain_ok:
        issue_text = "\n".join(issues)
        raise ValueError(f"selected snapshot window failed hash-chain verification:\n{issue_text}")

    git_sha = _git_sha()
    out_path = args.out
    if out_path.suffixes[-2:] != [".tar", ".gz"]:
        out_path.mkdir(parents=True, exist_ok=True)
        out_path = out_path / _default_bundle_name(window, git_sha, args.format)

    with tempfile.TemporaryDirectory() as temp_dir:
        bundle_root = Path(temp_dir)
        trend_report_source = DEFAULT_TREND_REPORT
        if not trend_report_source.exists():
            trend_report_source = bundle_root / DEFAULT_TREND_REPORT.name
            _regenerate_trend_report(window, trend_report_source)
        _copy_bundle_inputs(bundle_root, window, trend_report_source)
        manifest = _write_manifest(
            window=window,
            trend_report_name=DEFAULT_TREND_REPORT.name,
            manifest_path=bundle_root / "manifest.json",
            anchor_prev_hash=anchor_prev_hash,
        )
        _create_deterministic_tar_gz(bundle_root, out_path)

    manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    index_entry: dict[str, Any] = {
        "schema_version": 1,
        "created_at": _iso_timestamp(datetime.now().astimezone()),
        "bundle_path": str(out_path),
        "manifest_hash": hashlib.sha256(manifest_bytes).hexdigest(),
        "first_provenance_hash": str(manifest.get("first_provenance_hash", "")),
        "last_provenance_hash": str(manifest.get("last_provenance_hash", "")),
        "count": int(manifest.get("bundle_window", {}).get("count", 0)),
        "window_from": str(manifest.get("bundle_window", {}).get("from", "")),
        "window_to": str(manifest.get("bundle_window", {}).get("to", "")),
    }
    _append_archive_index_entry(args.archive_index, index_entry)

    print(
        f"Exported provenance bundle: {out_path} snapshots={len(window.snapshots)} "
        f"window={window.started_at}..{window.ended_at}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
