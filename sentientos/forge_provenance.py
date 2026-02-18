"""Tamper-evident Forge provenance ledger utilities."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
from typing import Any
import uuid


PROVENANCE_DIR = Path("glow/forge/provenance")
CHAIN_PATH = PROVENANCE_DIR / "chain.jsonl"
BLOBS_DIR = PROVENANCE_DIR / "blobs"
SCHEMA_VERSION = 1
MAX_BLOB_CHARS = 12000


@dataclass(slots=True)
class ProvenanceHeader:
    schema_version: int
    run_id: str
    started_at: str
    finished_at: str
    initiator: str
    request_id: str | None
    goal: str | None
    goal_id: str | None
    campaign_id: str | None
    transaction_status: str
    quarantine_ref: str | None


@dataclass(slots=True)
class ProvenanceStep:
    step_id: str
    kind: str
    command: dict[str, object]
    cwd: str
    env_fingerprint: str
    started_at: str
    finished_at: str
    exit_code: int
    stdout_digest: str
    stderr_digest: str
    artifacts_written: list[str]
    notes: str


@dataclass(slots=True)
class ProvenanceBundle:
    header: ProvenanceHeader
    repo_root_fingerprint: str
    env_cache_key: str
    python_version: str
    dependency_fingerprint: str
    before_snapshot_digest: str | None
    after_snapshot_digest: str | None
    steps: list[ProvenanceStep]
    final_artifact_index: list[dict[str, str]]


class ForgeProvenance:
    def __init__(self, repo_root: Path, *, run_id: str | None = None) -> None:
        self.repo_root = repo_root.resolve()
        self.run_id = run_id or str(uuid.uuid4())
        self._steps: list[ProvenanceStep] = []

    def build_header(self, *, started_at: str, finished_at: str, initiator: str, request_id: str | None, goal: str | None, goal_id: str | None, campaign_id: str | None, transaction_status: str, quarantine_ref: str | None) -> ProvenanceHeader:
        return ProvenanceHeader(
            schema_version=SCHEMA_VERSION,
            run_id=self.run_id,
            started_at=started_at,
            finished_at=finished_at,
            initiator=initiator,
            request_id=request_id,
            goal=goal,
            goal_id=goal_id,
            campaign_id=campaign_id,
            transaction_status=transaction_status,
            quarantine_ref=quarantine_ref,
        )

    def add_step(self, step: ProvenanceStep, *, stdout: str = "", stderr: str = "") -> None:
        self._write_blob(stdout)
        self._write_blob(stderr)
        self._steps.append(step)

    def make_step(self, *, step_id: str, kind: str, command: dict[str, object], cwd: str, env_fingerprint: str, started_at: str, finished_at: str, exit_code: int, stdout: str, stderr: str, artifacts_written: list[str], notes: str = "") -> ProvenanceStep:
        return ProvenanceStep(
            step_id=step_id,
            kind=kind,
            command=command,
            cwd=cwd,
            env_fingerprint=env_fingerprint,
            started_at=started_at,
            finished_at=finished_at,
            exit_code=exit_code,
            stdout_digest=_sha256_text(stdout),
            stderr_digest=_sha256_text(stderr),
            artifacts_written=artifacts_written,
            notes=notes,
        )

    def finalize(self, *, header: ProvenanceHeader, env_cache_key: str, before_snapshot: object | None, after_snapshot: object | None, artifacts: list[str]) -> tuple[Path, ProvenanceBundle, dict[str, str]]:
        bundle = ProvenanceBundle(
            header=header,
            repo_root_fingerprint=_repo_root_fingerprint(self.repo_root),
            env_cache_key=env_cache_key,
            python_version=platform.python_version(),
            dependency_fingerprint=_dependency_fingerprint(self.repo_root),
            before_snapshot_digest=_digest_json(before_snapshot),
            after_snapshot_digest=_digest_json(after_snapshot),
            steps=list(self._steps),
            final_artifact_index=_artifact_index(self.repo_root, artifacts),
        )
        out_path = PROVENANCE_DIR / f"prov_{self.run_id}.json"
        payload = _to_json(asdict(bundle))
        _write_text(self.repo_root / out_path, payload)
        entry = append_chain(self.repo_root, run_id=self.run_id, bundle_sha256=_sha256_text(payload))
        return out_path, bundle, entry

    def _write_blob(self, text: str) -> None:
        if not text:
            return
        digest = _sha256_text(text)
        target = self.repo_root / BLOBS_DIR / f"{digest}.txt"
        if target.exists():
            return
        clipped = text[:MAX_BLOB_CHARS]
        _write_text(target, clipped)


def append_chain(repo_root: Path, *, run_id: str, bundle_sha256: str) -> dict[str, str]:
    root = repo_root.resolve()
    entries = _read_chain(root)
    prev_sha = entries[-1]["chain_sha256"] if entries else ""
    timestamp = _iso_now()
    basis = json.dumps({"run_id": run_id, "bundle_sha256": bundle_sha256, "prev_sha256": prev_sha, "timestamp": timestamp}, sort_keys=True, separators=(",", ":"))
    chain_sha = _sha256_text(basis)
    row = {
        "run_id": run_id,
        "bundle_sha256": bundle_sha256,
        "prev_sha256": prev_sha,
        "chain_sha256": chain_sha,
        "timestamp": timestamp,
    }
    path = root / CHAIN_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    return row


def validate_chain(repo_root: Path) -> dict[str, object]:
    entries = _read_chain(repo_root.resolve())
    prev = ""
    for idx, row in enumerate(entries):
        basis = json.dumps({"run_id": row.get("run_id", ""), "bundle_sha256": row.get("bundle_sha256", ""), "prev_sha256": row.get("prev_sha256", ""), "timestamp": row.get("timestamp", "")}, sort_keys=True, separators=(",", ":"))
        expected = _sha256_text(basis)
        if str(row.get("prev_sha256", "")) != prev:
            return {"valid": False, "index": idx, "reason": "prev_mismatch", "last_run_id": row.get("run_id")}
        if str(row.get("chain_sha256", "")) != expected:
            return {"valid": False, "index": idx, "reason": "hash_mismatch", "last_run_id": row.get("run_id")}
        prev = expected
    last_run_id = entries[-1].get("run_id") if entries else None
    return {"valid": True, "count": len(entries), "last_run_id": last_run_id, "chain_head": prev or None}


def load_bundle(repo_root: Path, target: str) -> ProvenanceBundle:
    path = Path(target)
    if not path.exists():
        path = repo_root / PROVENANCE_DIR / f"prov_{target}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    header = ProvenanceHeader(**payload["header"])
    steps = [ProvenanceStep(**step) for step in payload.get("steps", [])]
    return ProvenanceBundle(
        header=header,
        repo_root_fingerprint=str(payload.get("repo_root_fingerprint", "")),
        env_cache_key=str(payload.get("env_cache_key", "")),
        python_version=str(payload.get("python_version", "")),
        dependency_fingerprint=str(payload.get("dependency_fingerprint", "")),
        before_snapshot_digest=payload.get("before_snapshot_digest"),
        after_snapshot_digest=payload.get("after_snapshot_digest"),
        steps=steps,
        final_artifact_index=[{"path": str(item.get("path", "")), "sha256": str(item.get("sha256", ""))} for item in payload.get("final_artifact_index", []) if isinstance(item, dict)],
    )


def _artifact_index(repo_root: Path, artifacts: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for artifact in sorted(set(artifacts)):
        path = Path(artifact)
        absolute = path if path.is_absolute() else repo_root / artifact
        if absolute.exists() and absolute.is_file():
            rows.append({"path": artifact, "sha256": _sha256_file(absolute)})
    return rows


def _repo_root_fingerprint(repo_root: Path) -> str:
    return _sha256_text(str(repo_root.resolve()))


def _dependency_fingerprint(repo_root: Path) -> str:
    digest = hashlib.sha256()
    candidates = ["pyproject.toml", "poetry.lock", "Pipfile.lock", "requirements.txt", "requirements-dev.txt", "requirements-test.txt"]
    found = False
    for name in candidates:
        path = repo_root / name
        if not path.exists():
            continue
        found = True
        digest.update(name.encode("utf-8"))
        digest.update(path.read_bytes())
    if not found:
        digest.update(b"no-deps")
    return digest.hexdigest()


def _read_chain(repo_root: Path) -> list[dict[str, str]]:
    path = repo_root / CHAIN_PATH
    if not path.exists():
        return []
    rows: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append({str(k): str(v) for k, v in payload.items()})
    return rows


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _digest_json(payload: object | None) -> str | None:
    if payload is None:
        return None
    return _sha256_text(json.dumps(payload, sort_keys=True, default=str))


def _to_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
