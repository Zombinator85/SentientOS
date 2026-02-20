"""GitHub Actions artifact discovery/download for per-SHA contract bundles."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile
from typing import Any, Literal
from urllib import error, request


@dataclass(slots=True)
class ArtifactRef:
    name: str
    url: str
    run_id: int
    sha: str
    created_at: str


@dataclass(slots=True)
class ContractBundle:
    sha: str
    paths: dict[str, str]
    parsed: dict[str, dict[str, object]]
    source: Literal["remote", "local"]
    errors: list[str] = field(default_factory=list)


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
        return _find_with_api(repo=repo, token=os.getenv("GITHUB_TOKEN", ""), pr_number=pr_number, sha=sha, expected_name=expected)
    return None


def download_contract_bundle(artifact_ref: ArtifactRef, dest_dir: Path) -> ContractBundle:
    target = dest_dir / artifact_ref.sha
    target.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    downloaded = False
    if shutil.which("gh") is not None:
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
    bundle = parse_bundle(target)
    bundle.sha = artifact_ref.sha
    bundle.errors.extend(errors)
    return bundle


def parse_bundle(bundle_dir: Path) -> ContractBundle:
    parsed: dict[str, dict[str, object]] = {}
    paths: dict[str, str] = {}
    errors: list[str] = []
    sha = ""
    expected = [
        "contract_status.json",
        "stability_doctrine.json",
        "ci_baseline.json",
        "forge_progress_baseline.json",
        "artifact_metadata.json",
    ]
    for name in expected:
        path = bundle_dir / name
        if not path.exists():
            if name != "forge_progress_baseline.json":
                errors.append(f"missing:{name}")
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
    return ContractBundle(sha=sha, paths=paths, parsed=parsed, source="remote", errors=errors)


def _capabilities() -> dict[str, bool]:
    return {"gh": shutil.which("gh") is not None, "token": bool(os.getenv("GITHUB_TOKEN"))}


def _find_with_gh(*, repo: str, pr_number: int | None, sha: str, expected_name: str) -> ArtifactRef | None:
    _ = pr_number
    payload = _run_gh_json(["gh", "api", f"repos/{repo}/actions/artifacts", "-f", "per_page=100"])
    return _pick_artifact(payload=payload, sha=sha, expected_name=expected_name)


def _find_with_api(*, repo: str, token: str, pr_number: int | None, sha: str, expected_name: str) -> ArtifactRef | None:
    _ = pr_number
    payload = _http_json(f"https://api.github.com/repos/{repo}/actions/artifacts?per_page=100", token)
    return _pick_artifact(payload=payload, sha=sha, expected_name=expected_name)


def _pick_artifact(*, payload: dict[str, object], sha: str, expected_name: str) -> ArtifactRef | None:
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        return None
    rows: list[dict[str, Any]] = [item for item in artifacts if isinstance(item, dict)]
    for row in rows:
        name = row.get("name")
        if not isinstance(name, str):
            continue
        if name != expected_name:
            continue
        workflow_raw = row.get("workflow_run")
        workflow_run: dict[str, Any] = workflow_raw if isinstance(workflow_raw, dict) else {}
        run_head = workflow_run.get("head_sha") if isinstance(workflow_run.get("head_sha"), str) else ""
        if run_head and run_head != sha:
            continue
        run_id = workflow_run.get("id")
        if not isinstance(run_id, int):
            continue
        url_raw = row.get("archive_download_url")
        created_raw = row.get("created_at")
        url = url_raw if isinstance(url_raw, str) else ""
        created_at = created_raw if isinstance(created_raw, str) else ""
        return ArtifactRef(name=name, url=url, run_id=run_id, sha=sha, created_at=created_at)
    return None


def _run_gh_json(argv: list[str]) -> dict[str, object]:
    proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return {}
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


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
