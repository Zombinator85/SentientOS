"""GitHub Actions artifact discovery/download for per-SHA contract bundles."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile
from typing import Any, Callable, Literal
from urllib import error, request


@dataclass(slots=True)
class ArtifactRef:
    name: str
    url: str
    run_id: int
    sha: str
    created_at: str
    selected_via: str = ""
    source: Literal["actions", "mirror_release"] = "actions"


@dataclass(slots=True)
class ContractBundle:
    sha: str
    paths: dict[str, str]
    parsed: dict[str, dict[str, object]]
    source: Literal["remote", "local"]
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)
    metadata_ok: bool = False
    manifest_ok: bool = False
    bundle_sha256: str = ""
    failing_hash_paths: list[str] = field(default_factory=list)
    mirror_used: bool = False


REQUIRED_BUNDLE_FILES: tuple[str, ...] = (
    "stability_doctrine.json",
    "contract_status.json",
    "artifact_metadata.json",
    "contract_manifest.json",
)
OPTIONAL_BUNDLE_FILES: tuple[str, ...] = (
    "ci_baseline.json",
    "forge_progress_baseline.json",
)


def find_contract_artifact_for_sha(pr_number: int | None, sha: str) -> ArtifactRef | None:
    if not sha:
        return None
    repo = os.getenv("GITHUB_REPOSITORY", "")
    if not repo:
        return None
    expected = f"sentientos-contracts-{sha}"
    caps = _capabilities()
    if caps["gh"]:
        by_gh = _find_with_gh(repo=repo, pr_number=pr_number, sha=sha, expected_name=expected)
        if by_gh is not None:
            return by_gh
    if caps["token"]:
        by_api = _find_with_api(repo=repo, token=os.getenv("GITHUB_TOKEN", ""), pr_number=pr_number, sha=sha, expected_name=expected)
        if by_api is not None:
            return by_api
    if os.getenv("SENTIENTOS_CONTRACT_MIRROR_FETCH", "0") == "1":
        return _find_mirror_release(repo=repo, sha=sha)
    return None


def download_contract_bundle(artifact_ref: ArtifactRef, dest_dir: Path) -> ContractBundle:
    target = dest_dir / artifact_ref.sha
    target.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    downloaded = False
    if artifact_ref.source == "actions" and shutil.which("gh") is not None:
        run = subprocess.run(
            ["gh", "run", "download", str(artifact_ref.run_id), "-n", artifact_ref.name, "-D", str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        downloaded = run.returncode == 0
        if not downloaded and run.stderr.strip():
            errors.append(f"gh_download_failed:{run.stderr.strip()[:180]}")
    if not downloaded:
        token = os.getenv("GITHUB_TOKEN", "")
        if token and artifact_ref.url:
            zip_path = target / f"{artifact_ref.name}.zip"
            if _download_zip(artifact_ref.url, token, zip_path):
                try:
                    with zipfile.ZipFile(zip_path, "r") as archive:
                        archive.extractall(target)
                except (OSError, zipfile.BadZipFile) as exc:
                    errors.append(f"zip_extract_failed:{exc}")
                downloaded = True
            else:
                errors.append("token_download_failed")
        else:
            errors.append("token_download_failed")
    bundle = parse_bundle(target)
    bundle.sha = artifact_ref.sha
    bundle.mirror_used = artifact_ref.source == "mirror_release"
    bundle.errors.extend(errors)
    _validate_bundle_metadata(bundle, artifact_ref=artifact_ref)
    return bundle


def parse_bundle(bundle_dir: Path) -> ContractBundle:
    parsed: dict[str, dict[str, object]] = {}
    paths: dict[str, str] = {}
    errors: list[str] = []
    sha = ""
    expected = [*REQUIRED_BUNDLE_FILES, *OPTIONAL_BUNDLE_FILES]
    for name in expected:
        path = bundle_dir / name
        if not path.exists():
            if name in REQUIRED_BUNDLE_FILES:
                errors.append(f"bundle_missing_required:{name}")
            continue
        paths[name] = str(path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            errors.append(f"invalid_json:{name}")
            continue
        if isinstance(payload, dict):
            parsed[name] = payload
            if not sha:
                raw_sha = payload.get("git_sha") or payload.get("sha")
                if isinstance(raw_sha, str):
                    sha = raw_sha
        else:
            errors.append(f"invalid_shape:{name}")
    metadata = parsed.get("artifact_metadata.json", {})
    bundle = ContractBundle(
        sha=sha,
        paths=paths,
        parsed=parsed,
        source="remote",
        errors=errors,
        metadata=metadata if isinstance(metadata, dict) else {},
    )
    _validate_manifest(bundle, bundle_dir=bundle_dir)
    return bundle


def _validate_manifest(bundle: ContractBundle, *, bundle_dir: Path) -> None:
    manifest_raw = bundle.parsed.get("contract_manifest.json")
    if not isinstance(manifest_raw, dict):
        bundle.manifest_ok = False
        if "bundle_missing_required:contract_manifest.json" not in bundle.errors:
            bundle.errors.append("manifest_missing")
        return

    required_files = _as_str_list(manifest_raw.get("required_files"))
    optional_files = _as_str_list(manifest_raw.get("optional_files"))
    if not required_files:
        required_files = list(REQUIRED_BUNDLE_FILES)
    if not optional_files:
        optional_files = list(OPTIONAL_BUNDLE_FILES)
    file_hashes_raw = manifest_raw.get("file_sha256")
    file_hashes = file_hashes_raw if isinstance(file_hashes_raw, dict) else {}
    failing: list[str] = []

    for rel_path in [*required_files, *optional_files]:
        candidate = bundle_dir / rel_path
        if not candidate.exists():
            continue
        manifest_hash = file_hashes.get(rel_path)
        if not isinstance(manifest_hash, str) or not manifest_hash:
            failing.append(rel_path)
            continue
        file_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
        if file_hash != manifest_hash:
            failing.append(rel_path)

    canonical = "".join(f"{path}\n{digest}\n" for path, digest in sorted((k, v) for k, v in file_hashes.items() if isinstance(k, str) and isinstance(v, str)))
    recomputed = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    manifest_bundle = manifest_raw.get("bundle_sha256")
    if not isinstance(manifest_bundle, str) or recomputed != manifest_bundle:
        if "bundle_sha256" not in failing:
            failing.append("bundle_sha256")

    bundle.failing_hash_paths = failing
    bundle.bundle_sha256 = manifest_bundle if isinstance(manifest_bundle, str) else ""
    bundle.manifest_ok = not failing
    if failing:
        bundle.errors.append("manifest_mismatch")


def _as_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _capabilities() -> dict[str, bool]:
    return {"gh": shutil.which("gh") is not None, "token": bool(os.getenv("GITHUB_TOKEN"))}


def _find_with_gh(*, repo: str, pr_number: int | None, sha: str, expected_name: str) -> ArtifactRef | None:
    run = _find_from_runs(
        fetch_runs=lambda: _run_gh_pages(["gh", "api", f"repos/{repo}/actions/runs", "-f", "event=pull_request", "-f", f"head_sha={sha}", "-f", "per_page=100"]),
        fetch_run_artifacts=lambda run_id: _run_gh_pages(["gh", "api", f"repos/{repo}/actions/runs/{run_id}/artifacts", "-f", "per_page=100"]),
        sha=sha,
        expected_name=expected_name,
        pr_number=pr_number,
        selected_via="gh:run-artifacts",
    )
    if run is not None:
        return run
    return _find_from_global(
        pages=_run_gh_pages(["gh", "api", f"repos/{repo}/actions/artifacts", "-f", "per_page=100", "-f", f"name={expected_name}"]),
        sha=sha,
        expected_name=expected_name,
        pr_number=pr_number,
        selected_via="gh:global-listing",
    )


def _find_with_api(*, repo: str, token: str, pr_number: int | None, sha: str, expected_name: str) -> ArtifactRef | None:
    run = _find_from_runs(
        fetch_runs=lambda: _http_json_pages(f"https://api.github.com/repos/{repo}/actions/runs?event=pull_request&head_sha={sha}&per_page=100", token),
        fetch_run_artifacts=lambda run_id: _http_json_pages(f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100", token),
        sha=sha,
        expected_name=expected_name,
        pr_number=pr_number,
        selected_via="api:run-artifacts",
    )
    if run is not None:
        return run
    return _find_from_global(
        pages=_http_json_pages(f"https://api.github.com/repos/{repo}/actions/artifacts?per_page=100&name={expected_name}", token),
        sha=sha,
        expected_name=expected_name,
        pr_number=pr_number,
        selected_via="api:global-listing",
    )


def _find_from_runs(
    *,
    fetch_runs: Callable[[], list[dict[str, object]]],
    fetch_run_artifacts: Callable[[int], list[dict[str, object]]],
    sha: str,
    expected_name: str,
    pr_number: int | None,
    selected_via: str,
) -> ArtifactRef | None:
    pages = fetch_runs()
    runs: list[dict[str, Any]] = []
    for payload in pages:
        rows = payload.get("workflow_runs")
        if isinstance(rows, list):
            runs.extend(item for item in rows if isinstance(item, dict))

    ordered_runs = sorted(runs, key=lambda item: int(item.get("id", 0)), reverse=True)
    for run in ordered_runs:
        run_id = run.get("id")
        if not isinstance(run_id, int):
            continue
        head_sha = run.get("head_sha") if isinstance(run.get("head_sha"), str) else ""
        if head_sha != sha:
            continue
        if pr_number is not None and not _run_has_pr(run, pr_number):
            continue
        pages_for_run = fetch_run_artifacts(run_id)
        candidate = _pick_artifact(
            pages=pages_for_run,
            sha=sha,
            expected_name=expected_name,
            pr_number=pr_number,
            run_id=run_id,
            selected_via=selected_via,
        )
        if candidate is not None:
            return candidate
    return None


def _find_from_global(*, pages: list[dict[str, object]], sha: str, expected_name: str, pr_number: int | None, selected_via: str) -> ArtifactRef | None:
    return _pick_artifact(pages=pages, sha=sha, expected_name=expected_name, pr_number=pr_number, run_id=None, selected_via=selected_via)


def _pick_artifact(*, pages: list[dict[str, object]], sha: str, expected_name: str, pr_number: int | None, run_id: int | None, selected_via: str) -> ArtifactRef | None:
    matches: list[dict[str, Any]] = []
    for payload in pages:
        artifacts = payload.get("artifacts")
        if not isinstance(artifacts, list):
            continue
        for row in artifacts:
            if not isinstance(row, dict):
                continue
            name = row.get("name")
            if name != expected_name:
                continue
            workflow_raw = row.get("workflow_run")
            workflow_run: dict[str, Any] = workflow_raw if isinstance(workflow_raw, dict) else {}
            row_run_id = workflow_run.get("id") if isinstance(workflow_run.get("id"), int) else run_id
            if not isinstance(row_run_id, int):
                continue
            if run_id is not None and row_run_id != run_id:
                continue
            run_head = workflow_run.get("head_sha") if isinstance(workflow_run.get("head_sha"), str) else ""
            if run_head and run_head != sha:
                continue
            if pr_number is not None and workflow_run and not _run_has_pr(workflow_run, pr_number):
                continue
            if row.get("expired") is True:
                continue
            created_at = row.get("created_at") if isinstance(row.get("created_at"), str) else ""
            matches.append({"row": row, "run_id": row_run_id, "created_at": created_at})

    if not matches:
        return None
    matches.sort(key=lambda item: (item["created_at"], item["run_id"]), reverse=True)
    chosen = matches[0]
    row = chosen["row"]
    url_raw = row.get("archive_download_url")
    url = url_raw if isinstance(url_raw, str) else ""
    created_at = chosen["created_at"] if isinstance(chosen["created_at"], str) else ""
    return ArtifactRef(name=expected_name, url=url, run_id=int(chosen["run_id"]), sha=sha, created_at=created_at, selected_via=selected_via)


def _run_has_pr(run: dict[str, Any], pr_number: int) -> bool:
    pull_requests = run.get("pull_requests")
    if not isinstance(pull_requests, list):
        return False
    for row in pull_requests:
        if not isinstance(row, dict):
            continue
        if row.get("number") == pr_number:
            return True
    return False


def _run_gh_json(argv: list[str]) -> dict[str, object]:
    proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return {}
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _run_gh_pages(argv: list[str]) -> list[dict[str, object]]:
    payload = _run_gh_json([*argv, "--paginate", "--slurp"])
    if payload:
        return [payload]
    proc = subprocess.run([*argv, "--paginate", "--slurp"], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return []
    try:
        loaded = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(loaded, list):
        return [item for item in loaded if isinstance(item, dict)]
    if isinstance(loaded, dict):
        return [loaded]
    return []


def _http_json(url: str, token: str) -> dict[str, object]:
    req = request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    try:
        with request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (error.URLError, TimeoutError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _http_json_pages(url: str, token: str) -> list[dict[str, object]]:
    pages: list[dict[str, object]] = []
    page = 1
    while page <= 20:
        sep = "&" if "?" in url else "?"
        payload = _http_json(f"{url}{sep}page={page}", token)
        if not payload:
            break
        pages.append(payload)
        has_runs = isinstance(payload.get("workflow_runs"), list) and bool(payload.get("workflow_runs"))
        has_artifacts = isinstance(payload.get("artifacts"), list) and bool(payload.get("artifacts"))
        if not has_runs and not has_artifacts:
            break
        page += 1
    return pages


def _validate_bundle_metadata(bundle: ContractBundle, *, artifact_ref: ArtifactRef) -> None:
    metadata = bundle.metadata
    mismatches: list[str] = []
    if not metadata:
        bundle.metadata_ok = False
        return
    sha_raw = metadata.get("sha") if isinstance(metadata.get("sha"), str) else metadata.get("git_sha")
    if isinstance(sha_raw, str) and sha_raw and sha_raw != artifact_ref.sha:
        mismatches.append("metadata_mismatch:sha")
    repo = os.getenv("GITHUB_REPOSITORY", "")
    metadata_repo = metadata.get("repository")
    if repo and isinstance(metadata_repo, str) and metadata_repo and metadata_repo != repo:
        mismatches.append("metadata_mismatch:repository")
    metadata_run_id = metadata.get("run_id")
    if artifact_ref.source == "actions" and isinstance(metadata_run_id, int) and metadata_run_id != artifact_ref.run_id:
        mismatches.append("metadata_mismatch:run_id")
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        if key.endswith("_at") or "timestamp" in key:
            if not _is_iso_timestamp(value):
                mismatches.append(f"metadata_invalid_timestamp:{key}")
    bundle.errors.extend(mismatches)
    bundle.metadata_ok = not any(item.startswith("metadata_mismatch:") for item in mismatches)


def _is_iso_timestamp(value: str) -> bool:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _download_zip(url: str, token: str, target: Path) -> bool:
    req = request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    try:
        with request.urlopen(req, timeout=30) as resp:
            target.write_bytes(resp.read())
    except (error.URLError, TimeoutError, OSError):
        return False
    return True


def _find_mirror_release(*, repo: str, sha: str) -> ArtifactRef | None:
    asset_name = f"sentientos-contracts-{sha}.zip"
    caps = _capabilities()
    if caps["gh"]:
        payload = _run_gh_json(["gh", "api", f"repos/{repo}/releases/tags/contracts-{sha}"])
    elif caps["token"]:
        payload = _http_json(f"https://api.github.com/repos/{repo}/releases/tags/contracts-{sha}", os.getenv("GITHUB_TOKEN", ""))
    else:
        return None
    assets = payload.get("assets")
    if not isinstance(assets, list):
        return None
    for item in assets:
        if not isinstance(item, dict):
            continue
        if item.get("name") != asset_name:
            continue
        download_url = item.get("browser_download_url")
        if not isinstance(download_url, str) or not download_url:
            continue
        raw_created_at = payload.get("published_at")
        created_at = raw_created_at if isinstance(raw_created_at, str) else ""
        return ArtifactRef(name=asset_name, url=download_url, run_id=0, sha=sha, created_at=created_at, selected_via="mirror:release", source="mirror_release")
    return None
