from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
from typing import Any

from sentientos.artifact_catalog import append_catalog_entry

STATUS_PATH = Path("glow/federation/anchor_witness_status.json")


def maybe_publish_anchor_witness(repo_root: Path) -> tuple[dict[str, object], str | None]:
    if os.getenv("SENTIENTOS_ANCHOR_WITNESS_PUBLISH", "0") != "1":
        status = {
            "witness_status": "disabled",
            "last_witness_published_at": None,
            "last_witness_anchor_id": None,
            "witness_failure": None,
        }
        _write_status(repo_root, status)
        return status, None

    backend = os.getenv("SENTIENTOS_ANCHOR_WITNESS_BACKEND", "git")
    if backend == "file":
        status, failure = _publish_file_backend(repo_root)
    else:
        status, failure = _publish_git_tag(repo_root)
    _write_status(repo_root, status)

    if failure and os.getenv("SENTIENTOS_ANCHOR_WITNESS_ENFORCE", "0") == "1":
        return status, f"witness_publish_failed:{failure}"
    return status, None


def _publish_file_backend(repo_root: Path) -> tuple[dict[str, object], str | None]:
    anchor = _latest_anchor(repo_root)
    if not anchor:
        return _failed(None, "anchor_missing"), "anchor_missing"
    anchor_id = _as_str(anchor.get("anchor_id"))
    if not anchor_id:
        return _failed(None, "anchor_id_missing"), "anchor_id_missing"
    log_path = Path(os.getenv("SENTIENTOS_ANCHOR_WITNESS_LOG", str(repo_root / "glow/federation/witness_log.jsonl")))
    rows = _read_jsonl(log_path)
    if any(_as_str(row.get("anchor_id")) == anchor_id for row in rows):
        return _ok(anchor_id, _as_str(rows[-1].get("published_at"))) if rows else _ok(anchor_id, None), None
    message = _summary(anchor)
    row = {"anchor_id": anchor_id, "published_at": _iso_now(), "summary": message}
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    return _ok(anchor_id, _as_str(row.get("published_at"))), None


def _publish_git_tag(repo_root: Path) -> tuple[dict[str, object], str | None]:
    anchor = _latest_anchor(repo_root)
    if not anchor:
        return _failed(None, "anchor_missing"), "anchor_missing"
    anchor_id = _as_str(anchor.get("anchor_id"))
    if not anchor_id:
        return _failed(None, "anchor_id_missing"), "anchor_id_missing"
    tag = f"sentientos-anchor/{anchor_id}"
    if _git_tag_exists(repo_root, tag):
        return _ok(anchor_id, None), None

    message = _summary(anchor)
    sign = os.getenv("SENTIENTOS_ANCHOR_WITNESS_SIGN", "0") == "1"
    cmd = ["git", "tag", "-s" if sign else "-a", tag, "-m", message]
    completed = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "tag_create_failed"
        return _failed(anchor_id, detail), detail

    if os.getenv("SENTIENTOS_ANCHOR_WITNESS_PUSH", "0") == "1":
        remote = os.getenv("SENTIENTOS_ANCHOR_WITNESS_REMOTE", "origin")
        push = subprocess.run(["git", "push", remote, tag], cwd=repo_root, capture_output=True, text=True, check=False)
        if push.returncode != 0:
            detail = push.stderr.strip() or push.stdout.strip() or "tag_push_failed"
            return _failed(anchor_id, detail), detail

    return _ok(anchor_id, _iso_now()), None


def _latest_anchor(repo_root: Path) -> dict[str, object]:
    anchors = sorted((repo_root / "glow/forge/receipts/anchors").glob("anchor_*.json"), key=lambda item: item.name)
    if not anchors:
        return {}
    return _read_json(anchors[-1])


def _summary(anchor: dict[str, object]) -> str:
    lines = [
        f"anchor_id: {_as_str(anchor.get('anchor_id')) or ''}",
        f"created_at: {_as_str(anchor.get('created_at')) or ''}",
        f"receipt_chain_tip_hash: {_as_str(anchor.get('receipt_chain_tip_hash')) or ''}",
        f"receipts_index_sha256: {_as_str(anchor.get('receipts_index_sha256')) or ''}",
        f"anchor_payload_sha256: {_as_str(anchor.get('anchor_payload_sha256')) or ''}",
        f"public_key_id: {_as_str(anchor.get('public_key_id')) or ''}",
        f"algorithm: {_as_str(anchor.get('algorithm')) or ''}",
    ]
    return "\n".join(lines)


def _ok(anchor_id: str, published_at: str | None) -> dict[str, object]:
    return {
        "witness_status": "ok",
        "last_witness_published_at": published_at,
        "last_witness_anchor_id": anchor_id,
        "witness_failure": None,
    }


def _failed(anchor_id: str | None, failure: str) -> dict[str, object]:
    return {
        "witness_status": "failed",
        "last_witness_published_at": None,
        "last_witness_anchor_id": anchor_id,
        "witness_failure": failure[:240],
    }


def _git_tag_exists(repo_root: Path, tag: str) -> bool:
    completed = subprocess.run(["git", "rev-parse", "--verify", f"refs/tags/{tag}"], cwd=repo_root, capture_output=True, text=True, check=False)
    return completed.returncode == 0


def _write_status(repo_root: Path, status: dict[str, object]) -> None:
    target = repo_root / STATUS_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    ts = _as_str(status.get("last_witness_published_at")) or _iso_now()
    append_catalog_entry(
        repo_root,
        kind="witness_publish",
        artifact_id=_as_str(status.get("last_witness_anchor_id")) or f"witness:{ts}",
        relative_path=str(STATUS_PATH),
        schema_name="witness_publish",
        schema_version=1,
        links={"anchor_id": status.get("last_witness_anchor_id")},
        summary={"witness_status": status.get("witness_status"), "witness_failure": status.get("witness_failure")},
        ts=ts,
    )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows: list[dict[str, object]] = []
    for line in lines:
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


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
