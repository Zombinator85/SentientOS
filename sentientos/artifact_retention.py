from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any


RETENTION_STATE_PATH = Path("glow/forge/retention/state.json")
RETENTION_REPORT_DIR = Path("glow/forge/retention")
REDIRECTS_PATH = Path("glow/forge/archive/redirects.jsonl")


@dataclass(frozen=True)
class RetentionPolicy:
    enabled: bool
    keep_days_ticks: int
    keep_days_sweeps: int
    keep_days_runs: int
    keep_days_catalog: int
    archive_dir: Path
    rollup_interval_days: int

    @classmethod
    def from_env(cls) -> "RetentionPolicy":
        return cls(
            enabled=os.getenv("SENTIENTOS_RETENTION_ENABLE", "0") == "1",
            keep_days_ticks=max(1, _env_int("SENTIENTOS_RETENTION_KEEP_DAYS_TICKS", 14)),
            keep_days_sweeps=max(1, _env_int("SENTIENTOS_RETENTION_KEEP_DAYS_SWEEPS", 30)),
            keep_days_runs=max(1, _env_int("SENTIENTOS_RETENTION_KEEP_DAYS_RUNS", 60)),
            keep_days_catalog=max(1, _env_int("SENTIENTOS_RETENTION_KEEP_DAYS_CATALOG", 180)),
            archive_dir=Path(os.getenv("SENTIENTOS_RETENTION_ARCHIVE_DIR", "glow/forge/archive")),
            rollup_interval_days=max(1, _env_int("SENTIENTOS_RETENTION_ROLLUP_INTERVAL_DAYS", 7)),
        )


@dataclass(frozen=True)
class RetentionResult:
    ran: bool
    generated_at: str
    rollup_files: list[str]
    archived_items: int
    redirects_appended: int
    archive_moves: list[dict[str, str]]

    def to_dict(self) -> dict[str, object]:
        return {
            "ran": self.ran,
            "generated_at": self.generated_at,
            "rollup_files": self.rollup_files,
            "archived_items": self.archived_items,
            "redirects_appended": self.redirects_appended,
            "archive_moves": self.archive_moves,
        }


def run_retention(repo_root: Path, *, policy: RetentionPolicy | None = None, now: datetime | None = None) -> RetentionResult:
    root = repo_root.resolve()
    active = policy or RetentionPolicy.from_env()
    current = now.astimezone(timezone.utc) if now is not None else datetime.now(timezone.utc)
    generated_at = _iso(current)
    if not active.enabled:
        return RetentionResult(False, generated_at, [], 0, 0, [])

    rollup_files = _build_rollups(root, current, active)
    archive_moves = _archive_old_artifacts(root, current, active)
    _write_state(root, generated_at, rollup_files, archive_moves)

    return RetentionResult(
        ran=True,
        generated_at=generated_at,
        rollup_files=rollup_files,
        archived_items=len(archive_moves),
        redirects_appended=len(archive_moves),
        archive_moves=archive_moves,
    )


def should_run_retention(repo_root: Path, *, now: datetime | None = None, cooldown_days: int = 1) -> bool:
    root = repo_root.resolve()
    current = now.astimezone(timezone.utc) if now is not None else datetime.now(timezone.utc)
    state = load_retention_state(root)
    last_run = _parse_iso(_as_str(state.get("last_retention_run_at")))
    if last_run is None:
        return True
    return current - last_run >= timedelta(days=max(cooldown_days, 1))


def load_retention_state(repo_root: Path) -> dict[str, object]:
    path = repo_root.resolve() / RETENTION_STATE_PATH
    return _load_json(path)


def resolve_redirect(repo_root: Path, relative_path: str) -> str | None:
    mapping: dict[str, str] = {}
    for row in _read_jsonl(repo_root.resolve() / REDIRECTS_PATH):
        old_path = _as_str(row.get("old_path"))
        new_path = _as_str(row.get("new_path"))
        if old_path and new_path:
            mapping[old_path] = new_path
    return mapping.get(relative_path)


def redirect_count(repo_root: Path) -> int:
    rows = _read_jsonl(repo_root.resolve() / REDIRECTS_PATH)
    return len(rows)


def rollup_status(repo_root: Path) -> str:
    root = repo_root.resolve()
    rollup_root = root / "glow/forge/rollups"
    streams = sorted((root / "pulse").glob("*.jsonl"), key=lambda item: item.name)
    if not streams:
        return "ok"
    for stream in streams:
        name = stream.stem
        target_dir = rollup_root / name
        if not target_dir.exists() or not any(target_dir.glob("rollup_*.json")):
            return "missing"
    return "ok"


def _build_rollups(repo_root: Path, now: datetime, policy: RetentionPolicy) -> list[str]:
    root = repo_root.resolve()
    pulse = root / "pulse"
    if not pulse.exists():
        return []
    produced: list[str] = []
    for stream in sorted(pulse.glob("*.jsonl"), key=lambda item: item.name):
        rows = _read_jsonl(stream)
        if not rows:
            continue
        grouped: dict[str, list[dict[str, object]]] = {}
        for row in rows:
            row_ts = _parse_iso(_extract_ts(row))
            if row_ts is None:
                continue
            if now - row_ts < timedelta(days=policy.rollup_interval_days):
                continue
            week = f"{row_ts.isocalendar().year}-{row_ts.isocalendar().week:02d}"
            grouped.setdefault(week, []).append(row)
        for week, group_rows in sorted(grouped.items()):
            payload = _rollup_payload(stream.stem, week, group_rows)
            path = root / "glow/forge/rollups" / stream.stem / f"rollup_{week}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            produced.append(str(path.relative_to(root)))
    return produced


def _rollup_payload(stream_name: str, week: str, rows: list[dict[str, object]]) -> dict[str, object]:
    counts_by_day: dict[str, int] = {}
    key_frequency: dict[str, int] = {}
    for row in rows:
        ts = _parse_iso(_extract_ts(row))
        if ts is None:
            continue
        day_key = ts.date().isoformat()
        counts_by_day[day_key] = counts_by_day.get(day_key, 0) + 1
        for key in sorted(row.keys()):
            key_frequency[key] = key_frequency.get(key, 0) + 1
    canonical = [json.dumps(row, sort_keys=True, separators=(",", ":")) for row in rows]
    digest = hashlib.sha256("\n".join(canonical).encode("utf-8")).hexdigest()
    return {
        "schema_version": 1,
        "stream": stream_name,
        "rollup_week": week,
        "row_count": len(rows),
        "counts_by_day": [{"day": day, "count": counts_by_day[day]} for day in sorted(counts_by_day)],
        "observed_keys": [{"key": key, "count": key_frequency[key]} for key in sorted(key_frequency)],
        "content_sha256": digest,
    }


def _archive_old_artifacts(repo_root: Path, now: datetime, policy: RetentionPolicy) -> list[dict[str, str]]:
    root = repo_root.resolve()
    targets = [
        ("tick", root / "glow/forge/orchestrator/ticks", policy.keep_days_ticks),
        ("sweep", root / "glow/forge/sweeps", policy.keep_days_sweeps),
        ("run", root / "glow/forge/remediation/runs", policy.keep_days_runs),
    ]
    moves: list[dict[str, str]] = []
    for kind, base_dir, keep_days in targets:
        if not base_dir.exists():
            continue
        for path in sorted(base_dir.glob("*.json"), key=lambda item: item.name):
            modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if now - modified < timedelta(days=keep_days):
                continue
            month_dir = policy.archive_dir / kind / f"{modified.year:04d}" / f"{modified.month:02d}"
            destination = root / month_dir / path.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                continue
            path.rename(destination)
            old_rel = str(path.relative_to(root))
            new_rel = str(destination.relative_to(root))
            move = {"kind": kind, "old_path": old_rel, "new_path": new_rel}
            _append_jsonl(root / REDIRECTS_PATH, {
                "ts": _iso(now),
                "kind": kind,
                "old_path": old_rel,
                "new_path": new_rel,
            })
            _append_archive_catalog_entry(root, kind=kind, artifact_id=f"{kind}:{path.name}", relative_path=new_rel, old_path=old_rel, ts=_iso(now))
            moves.append(move)
    return moves


def _write_state(repo_root: Path, generated_at: str, rollup_files: list[str], archive_moves: list[dict[str, str]]) -> None:
    root = repo_root.resolve()
    payload = {
        "schema_version": 1,
        "last_retention_run_at": generated_at,
        "retention_last_summary": {
            "rollup_files": len(rollup_files),
            "archived_items": len(archive_moves),
        },
        "rollup_files": rollup_files,
        "archive_moves": archive_moves,
    }
    path = root / RETENTION_STATE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report_path = root / RETENTION_REPORT_DIR / f"retention_run_{_safe_ts(generated_at)}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _extract_ts(row: dict[str, object]) -> str | None:
    for key in ("generated_at", "created_at", "ts", "attempted_at", "timestamp"):
        value = _as_str(row.get(key))
        if value:
            return value
    return None


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def _append_jsonl(path: Path, row: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _load_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _safe_ts(value: str) -> str:
    return value.replace(":", "-").replace(".", "-")


def _iso(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _append_archive_catalog_entry(repo_root: Path, *, kind: str, artifact_id: str, relative_path: str, old_path: str, ts: str) -> None:
    row = {
        "schema_version": 1,
        "ts": ts,
        "kind": "archive_move",
        "id": artifact_id,
        "path": relative_path,
        "schema_name": "archive_move",
        "schema_version_artifact": 1,
        "links": {"trace_id": old_path},
        "summary": {"status": "archived", "kind": kind},
    }
    _append_jsonl(repo_root / "pulse/artifact_catalog.jsonl", row)
