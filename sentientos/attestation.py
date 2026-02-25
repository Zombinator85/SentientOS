from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess


VERIFY_STATUS_OK = "ok"
VERIFY_STATUS_WARN = "warn"
VERIFY_STATUS_FAIL = "fail"
VERIFY_STATUS_SKIPPED = "skipped"

WITNESS_STATUS_OK = "ok"
WITNESS_STATUS_FAILED = "failed"
WITNESS_STATUS_DISABLED = "disabled"
WITNESS_STATUS_SKIPPED_MUTATION_DISALLOWED = "skipped_mutation_disallowed"
WITNESS_STATUS_SKIPPED_REPO_DIRTY = "skipped_repo_dirty"
WITNESS_STATUS_SKIPPED_BACKEND_DISABLED = "skipped_backend_disabled"


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    status: str
    reason: str | None
    checked_n: int
    last_ok_hash: str | None


@dataclass(frozen=True)
class VerifyPolicy:
    enabled: bool
    last_n: int
    warn: bool
    enforce: bool


@dataclass(frozen=True)
class WitnessResult:
    status: str
    published_at: str | None
    failure: str | None
    tag: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "published_at": self.published_at,
            "failure": self.failure,
            "tag": self.tag,
        }


def canonical_json_bytes(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def compute_envelope_hash(payload: dict[str, object], *, hash_field: str) -> str:
    item = dict(payload)
    item.pop(hash_field, None)
    return _sha256_bytes(canonical_json_bytes(item))


def resolve_recent_rows(*, index_path: Path, sig_dir: Path, sig_glob: str, last_n: int) -> list[dict[str, object]]:
    rows = read_jsonl(index_path)
    if not rows:
        rows = [read_json(path) for path in sorted(sig_dir.glob(sig_glob), key=lambda p: p.name)]
    clean = [row for row in rows if row]
    if last_n > 0:
        clean = clean[-last_n:]
    return clean


def parse_verify_policy(*, enable_env: str, last_n_env: str, warn_env: str, enforce_env: str, default_last_n: int) -> VerifyPolicy:
    enabled = os.getenv(enable_env, "0") == "1"
    last_n = max(1, _env_int(last_n_env, default_last_n))
    enforce = os.getenv(enforce_env, "0") == "1"
    warn = os.getenv(warn_env, "0") == "1"
    if not enforce and not warn:
        warn = True
    return VerifyPolicy(enabled=enabled, last_n=last_n, warn=warn, enforce=enforce)


def signing_mode(env_name: str, *, default: str = "off") -> str:
    return os.getenv(env_name, default)


def witness_enabled(env_name: str) -> bool:
    return os.getenv(env_name, "0") == "1"


def publish_witness(
    *,
    repo_root: Path,
    backend: str,
    tag: str,
    message: str,
    file_path: Path,
    file_row: dict[str, object],
    allow_git_tag_publish: bool,
) -> WitnessResult:
    root = repo_root.resolve()
    if backend in {"off", "disabled", "none"}:
        return WitnessResult(status=WITNESS_STATUS_SKIPPED_BACKEND_DISABLED, published_at=None, failure="backend_disabled", tag=tag)
    if backend == "file":
        existing = {str(item.get("tag")) for item in read_jsonl(file_path) if isinstance(item.get("tag"), str)}
        if tag not in existing:
            append_jsonl(file_path, file_row)
        return WitnessResult(status=WITNESS_STATUS_OK, published_at=_iso_now(), failure=None, tag=tag)

    if not allow_git_tag_publish:
        return WitnessResult(
            status=WITNESS_STATUS_SKIPPED_MUTATION_DISALLOWED,
            published_at=None,
            failure="mutation_disallowed",
            tag=tag,
        )
    if not _git_repo_clean(root):
        return WitnessResult(status=WITNESS_STATUS_SKIPPED_REPO_DIRTY, published_at=None, failure="repo_dirty", tag=tag)
    if _git_tag_exists(root, tag):
        return WitnessResult(status=WITNESS_STATUS_OK, published_at=None, failure=None, tag=tag)
    completed = subprocess.run(["git", "tag", "-a", tag, "-m", message], cwd=root, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = (completed.stderr.strip() or completed.stdout.strip() or "tag_create_failed")[:240]
        return WitnessResult(status=WITNESS_STATUS_FAILED, published_at=None, failure=detail, tag=tag)
    return WitnessResult(status=WITNESS_STATUS_OK, published_at=_iso_now(), failure=None, tag=tag)


def read_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def read_jsonl(path: Path) -> list[dict[str, object]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, object]] = []
    for line in lines:
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            out.append(payload)
    return out


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def as_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def iso_now() -> str:
    return _iso_now()


def safe_ts(value: str) -> str:
    return value.replace(":", "-").replace(".", "-")


def _sha256_bytes(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def _git_tag_exists(repo_root: Path, tag: str) -> bool:
    completed = subprocess.run(["git", "rev-parse", "--verify", f"refs/tags/{tag}"], cwd=repo_root, capture_output=True, text=True, check=False)
    return completed.returncode == 0


def _git_repo_clean(repo_root: Path) -> bool:
    completed = subprocess.run(["git", "status", "--porcelain"], cwd=repo_root, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        return False
    return completed.stdout.strip() == ""


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default
