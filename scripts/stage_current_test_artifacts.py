from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "sentientos.current_test_artifacts:v1"
ALLOWED_NAMES = {
    "junitxml_path": ("pytest_junitxml_", ".xml", "pytest_junitxml.xml"),
    "failure_report_path": ("test_failure_digest", ".json", "test_failure_digest.json"),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_current_artifact(raw: Any, *, repo_root: Path, prefix: str, suffix: str) -> tuple[Path | None, str]:
    if not isinstance(raw, str) or not raw:
        return None, "not_recorded"
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        return None, "missing"
    run_root = (repo_root / "glow" / "test_runs").resolve()
    try:
        resolved.relative_to(run_root)
    except ValueError:
        return None, "outside_test_run_root"
    if not resolved.is_file():
        return None, "not_a_file"
    if not resolved.name.startswith(prefix) or resolved.suffix != suffix:
        return None, "unexpected_filename"
    return resolved, "staged"


def stage_current_test_artifacts(
    *,
    repo_root: Path,
    output_dir: Path,
    expected_repository_sha: str | None = None,
    started_after: Path | None = None,
) -> dict[str, object]:
    repo_root = repo_root.resolve(strict=True)
    provenance_path = repo_root / "glow" / "test_runs" / "test_run_provenance.json"
    try:
        provenance_bytes = provenance_path.read_bytes()
        provenance = json.loads(provenance_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"current test provenance is unavailable or invalid: {exc}") from exc
    if not isinstance(provenance, dict):
        raise ValueError("current test provenance must be a JSON object")

    provenance_mtime_ns = provenance_path.stat().st_mtime_ns
    cutoff_ns: int | None = None
    provenance_status = "current"
    if expected_repository_sha is not None and provenance.get("git_sha") != expected_repository_sha:
        provenance_status = "source_sha_mismatch"
    if started_after is not None:
        try:
            cutoff_ns = started_after.stat().st_mtime_ns
        except OSError:
            provenance_status = "start_marker_missing"
        else:
            if provenance_mtime_ns <= cutoff_ns:
                provenance_status = "stale_provenance"

    output_dir.mkdir(parents=True, exist_ok=True)
    for _, (_, _, output_name) in ALLOWED_NAMES.items():
        (output_dir / output_name).unlink(missing_ok=True)
    (output_dir / "current_test_artifacts.json").unlink(missing_ok=True)
    artifacts: dict[str, object] = {}
    for key, (prefix, suffix, output_name) in ALLOWED_NAMES.items():
        if provenance_status != "current":
            artifacts[key] = {"status": provenance_status}
            continue
        source, status = _resolve_current_artifact(
            provenance.get(key), repo_root=repo_root, prefix=prefix, suffix=suffix
        )
        record: dict[str, object] = {"status": status}
        if source is not None:
            destination = output_dir / output_name
            shutil.copyfile(source, destination)
            record.update(
                {
                    "source": source.relative_to(repo_root).as_posix(),
                    "sha256": _sha256(destination),
                    "size_bytes": destination.stat().st_size,
                }
            )
        artifacts[key] = record

    manifest: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "provenance_status": provenance_status,
        "provenance_sha256": hashlib.sha256(provenance_bytes).hexdigest(),
        "expected_repository_sha": expected_repository_sha,
        "provenance_mtime_ns": provenance_mtime_ns,
        "started_after_mtime_ns": cutoff_ns,
        "provenance_run_id": provenance.get("run_id"),
        "repository_sha": provenance.get("git_sha"),
        "validation_status": provenance.get("validation_status"),
        "tests_passed": provenance.get("tests_passed"),
        "tests_failed": provenance.get("tests_failed"),
        "artifacts": artifacts,
    }
    manifest_path = output_dir / "current_test_artifacts.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage only artifacts named by the current test provenance.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-repository-sha", required=True)
    parser.add_argument("--started-after", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = stage_current_test_artifacts(
            repo_root=args.repo_root,
            output_dir=args.output_dir,
            expected_repository_sha=args.expected_repository_sha,
            started_after=args.started_after,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
