from __future__ import annotations

import hashlib, json, os, subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "codex_landing_evidence_binding.v1"
PUBLICATION_HANDOFF_SCHEMA_VERSION = "sentientos.pr_publication_handoff:v1"
PUBLICATION_HANDOFF_READY = "pr_publication_handoff_ready"
HOSTED_PUBLICATION_SCHEMA_VERSION = "sentientos.hosted_pr_publication_custody:v1"
HOSTED_PUBLICATION_EXACT = "hosted_publication_custody_verified_exact"
HOSTED_PUBLICATION_REWRITTEN = "hosted_publication_head_rewritten_tree_equivalent_custody_break"
HOSTED_PUBLICATION_MISMATCH = "hosted_publication_mismatch"
HOSTED_PUBLICATION_INSUFFICIENT = "hosted_publication_observation_insufficient"
RUNTIME_PREFIXES = ("sentientos_data/vow", "sentientos_data/runtime", "glow/", "pulse/", "artifacts/codex/")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest_json(data: Any) -> str:
    return sha256_text(canonical_json(data))


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def artifact_digest(path_text: str | Path) -> str:
    return file_sha256(Path(path_text))


def run_git(repo: Path, *args: str) -> str:
    p = subprocess.run(["git", *args], cwd=repo, check=False, text=True, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout).strip() or f"git {' '.join(args)} failed")
    return p.stdout.strip()


def head_sha(repo: Path) -> str:
    return run_git(repo, "rev-parse", "HEAD")


def tree_sha(repo: Path, rev: str = "HEAD") -> str:
    return run_git(repo, "rev-parse", f"{rev}^{{tree}}")


def parent_sha(repo: Path, rev: str = "HEAD") -> str:
    out = run_git(repo, "rev-list", "--parents", "-n", "1", rev).split()
    return out[1] if len(out) > 1 else ""


def current_branch(repo: Path) -> tuple[str, bool]:
    name = run_git(repo, "branch", "--show-current")
    return name, not bool(name)


def resolve_repo_path(repo: Path, path_text: str) -> Path:
    if not path_text or "\x00" in path_text:
        raise ValueError("invalid_path")
    p = Path(path_text)
    if p.is_absolute():
        raise ValueError("path_outside_repository")
    root = repo.resolve()
    candidate_parent = (repo / p).parent.resolve()
    if candidate_parent != root and root not in candidate_parent.parents:
        raise ValueError("path_outside_repository")
    rel = (candidate_parent / (repo / p).name).relative_to(root).as_posix()
    if rel.startswith(".git/") or rel == ".git":
        raise ValueError("git_path_rejected")
    if any(rel == pre.rstrip("/") or rel.startswith(pre) for pre in RUNTIME_PREFIXES):
        raise ValueError("generated_runtime_path_rejected")
    return candidate_parent / (repo / p).name


def normalize_paths(repo: Path, paths: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set(); out: list[str] = []
    for raw in paths:
        candidate = resolve_repo_path(repo, raw)
        rel = candidate.relative_to(repo.resolve()).as_posix()
        if rel in seen:
            raise ValueError("canonical_duplicate_path")
        seen.add(rel); out.append(rel)
    return tuple(sorted(out))


@dataclass(frozen=True)
class LandingFileBinding:
    path: str
    posture: str
    mode: str
    sha256: str = ""
    symlink_target_sha256: str = ""


@dataclass(frozen=True)
class LandingWorkspaceBinding:
    schema_version: str
    base_head_sha: str
    intended_commit_title: str
    files: tuple[LandingFileBinding, ...]
    changed_path_manifest_digest: str
    focused_test_command_digest: str
    targeted_mypy_command_digest: str
    matrix_digest: str
    excluded_runtime_artifacts: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LandingCommitBinding:
    schema_version: str
    head_sha: str
    tree_sha: str
    parent_sha: str
    branch: str
    detached: bool
    commit_subject: str
    files: tuple[LandingFileBinding, ...]
    changed_path_manifest_digest: str
    pre_commit_workspace_manifest_digest: str
    matrix_digest: str
    finalizer_artifact_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LandingBodyBinding:
    schema_version: str
    title: str
    body_sha256: str
    body_byte_length: int
    commit_sha: str
    tree_sha: str
    matrix_digest: str
    artifact_digests: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LandingEvidenceVerification:
    status: str
    reasons: tuple[str, ...]
    proof: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PrPublicationHandoff:
    schema_version: str
    status: str
    repository: str
    intended_base_ref: str
    intended_base_sha: str
    intended_head_sha: str
    intended_head_tree_sha: str
    title: str
    body_sha256: str
    body_byte_length: int
    validation_profile: str
    exhaustive_matrix_status: str
    task_acceptance_manifest_sha256: str
    task_acceptance_provenance_sha256: str
    evidence_sha256: dict[str, str]
    boundary: dict[str, bool]
    handoff_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HostedPrPublicationCustody:
    schema_version: str
    status: str
    exact_publication_custody: bool
    handoff_sha256: str
    authorized_publication: dict[str, Any]
    hosted_observation: dict[str, Any]
    exact_hosted_body: dict[str, Any]
    equivalence: dict[str, Any]
    reasons: tuple[str, ...]
    boundary: dict[str, bool]
    custody_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _status_map(repo: Path) -> dict[str, str]:
    p = subprocess.run(["git", "status", "--porcelain=v1"], cwd=repo, text=True, capture_output=True, check=False)
    out: dict[str, str] = {}
    for line in p.stdout.splitlines():
        if not line: continue
        status = line[:2]; path = line[3:]
        if " -> " in path: path = path.split(" -> ", 1)[1]
        out[path] = status
    return out


def _bind_file(repo: Path, rel: str, deleted: bool = False, rev: str | None = None) -> LandingFileBinding:
    path = repo / rel
    if deleted:
        return LandingFileBinding(rel, "deleted", "000000")
    if rev:
        entry = run_git(repo, "ls-tree", rev, "--", rel)
        if not entry:
            return LandingFileBinding(rel, "deleted", "000000")
        mode = entry.split()[0]
        data = subprocess.run(["git", "show", f"{rev}:{rel}"], cwd=repo, check=True, capture_output=True).stdout
        if mode == "120000":
            return LandingFileBinding(rel, "symlink", mode, "", sha256_bytes(data))
        return LandingFileBinding(rel, "workspace", mode, sha256_bytes(data))
    if not path.exists() and not path.is_symlink():
        raise ValueError(f"missing_intended_file:{rel}")
    if path.is_symlink():
        target = os.readlink(path)
        return LandingFileBinding(rel, "symlink", "120000", "", sha256_text(target))
    mode = "100755" if os.access(path, os.X_OK) else "100644"
    return LandingFileBinding(rel, "workspace", mode, file_sha256(path))


def create_workspace_binding(repo: str | Path, *, intended_paths: Sequence[str], intended_commit_title: str, focused_test_commands: Sequence[str] = (), targeted_mypy_commands: Sequence[str] = (), matrix_json_path: str | Path | None = None, deleted_paths: Sequence[str] = ()) -> LandingWorkspaceBinding:
    root = Path(repo).resolve(); paths = normalize_paths(root, [*intended_paths, *deleted_paths]); deleted = set(normalize_paths(root, deleted_paths))
    dirty = _status_map(root)
    unknown = sorted(set(dirty) - set(paths))
    if unknown: raise ValueError("unknown_dirty_paths:" + ",".join(unknown))
    files = tuple(_bind_file(root, p, p in deleted) for p in paths)
    manifest = [asdict(f) for f in files]
    matrix_digest = file_sha256(Path(matrix_json_path)) if matrix_json_path else ""
    return LandingWorkspaceBinding(SCHEMA_VERSION, head_sha(root), intended_commit_title, files, digest_json(manifest), digest_json(list(focused_test_commands)), digest_json(list(targeted_mypy_commands)), matrix_digest, RUNTIME_PREFIXES)


def create_commit_binding(repo: str | Path, *, workspace_binding: LandingWorkspaceBinding | Mapping[str, Any], matrix_json_path: str | Path | None = None, finalizer_artifact_path: str | Path | None = None) -> LandingCommitBinding:
    root = Path(repo).resolve(); h = head_sha(root); branch, detached = current_branch(root)
    subject = run_git(root, "log", "-1", "--pretty=%s")
    wb_dict = workspace_binding.to_dict() if isinstance(workspace_binding, LandingWorkspaceBinding) else dict(workspace_binding)
    file_items = wb_dict.get("files", [])
    changed = [str(item.get("path", "")) for item in file_items if isinstance(item, Mapping)]
    if not changed:
        changed = run_git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", h).splitlines()
    files = tuple(_bind_file(root, p, rev=h) for p in sorted(changed) if p)
    matrix_digest = file_sha256(Path(matrix_json_path)) if matrix_json_path else str(wb_dict.get("matrix_digest", ""))
    return LandingCommitBinding(SCHEMA_VERSION, h, tree_sha(root), parent_sha(root), branch, detached, subject, files, digest_json([asdict(f) for f in files]), str(wb_dict.get("changed_path_manifest_digest", "")), matrix_digest, file_sha256(Path(finalizer_artifact_path)) if finalizer_artifact_path else "")


def verify_commit_matches_workspace(repo: str | Path, workspace: Mapping[str, Any], commit: Mapping[str, Any]) -> LandingEvidenceVerification:
    root = Path(repo).resolve(); reasons: list[str] = []
    if commit.get("schema_version") != SCHEMA_VERSION or workspace.get("schema_version") != SCHEMA_VERSION: reasons.append("binding_schema_missing")
    if commit.get("commit_subject") != workspace.get("intended_commit_title"): reasons.append("commit_title_mismatch")
    if commit.get("parent_sha") != workspace.get("base_head_sha"): reasons.append("commit_parent_mismatch")
    if commit.get("changed_path_manifest_digest") != workspace.get("changed_path_manifest_digest"): reasons.append("workspace_manifest_mismatch")
    if commit.get("matrix_digest") != workspace.get("matrix_digest"): reasons.append("matrix_digest_mismatch")
    try:
        if head_sha(root) != commit.get("head_sha"): reasons.append("current_head_changed_after_validation")
        if tree_sha(root) != commit.get("tree_sha"): reasons.append("commit_tree_mismatch")
    except Exception as exc: reasons.append(f"git_verification_failed:{type(exc).__name__}")
    return LandingEvidenceVerification("landing_evidence_binding_ready" if not reasons else "landing_evidence_binding_blocked", tuple(reasons), {"head_sha": commit.get("head_sha"), "tree_sha": commit.get("tree_sha"), "manifest_digest": commit.get("changed_path_manifest_digest"), "matrix_digest": commit.get("matrix_digest")})


def safe_runtime_roots(repo: str | Path, sandbox_root: str | Path | None, binding_id: str) -> dict[str, str]:
    root = Path(repo).resolve(); base = Path(sandbox_root or f"/tmp/sentientos-codex-finalizer/{binding_id}").resolve()
    if base == root or root in base.parents or ".git" in base.parts:
        raise ValueError("runtime_root_inside_workspace")
    return {"SENTIENTOS_DATA_DIR": str(base / "data"), "SENTIENTOS_RUNTIME_STATE_ROOT": str(base / "state")}


def create_body_binding(title: str, body_path: str | Path, commit: Mapping[str, Any], artifact_paths: Mapping[str, str]) -> LandingBodyBinding:
    body = Path(body_path).read_bytes(); artifacts = {k: file_sha256(Path(v)) for k, v in sorted(artifact_paths.items())}
    return LandingBodyBinding(SCHEMA_VERSION, title, sha256_bytes(body), len(body), str(commit.get("head_sha", "")), str(commit.get("tree_sha", "")), str(commit.get("matrix_digest", "")), artifacts)


def verify_body_binding(title: str, body_path: str | Path, sidecar: Mapping[str, Any], artifact_paths: Mapping[str, str]) -> LandingEvidenceVerification:
    reasons: list[str] = []; body = Path(body_path).read_bytes(); text = body.decode("utf-8", "replace")
    if title != sidecar.get("title"): reasons.append("title_mismatch")
    if sha256_bytes(body) != sidecar.get("body_sha256"): reasons.append("body_digest_mismatch")
    if len(body) != sidecar.get("body_byte_length"): reasons.append("body_length_mismatch")
    if len(text.strip()) < 600: reasons.append("evidence_light_body")
    if "$(cat" in text: reasons.append("literal_command_substitution")
    recorded = sidecar.get("artifact_digests", {}) if isinstance(sidecar.get("artifact_digests"), Mapping) else {}
    for name, path in artifact_paths.items():
        if recorded.get(name) != file_sha256(Path(path)): reasons.append(f"stale_artifact_digest:{name}")
    return LandingEvidenceVerification("pr_body_binding_ready" if not reasons else "pr_body_binding_blocked", tuple(reasons), {"body_sha256": sha256_bytes(body), "body_byte_length": len(body), "commit_sha": sidecar.get("commit_sha")})


def _json_object(path: str | Path, label: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label}_not_object")
    return value


def _decision_status(payload: Mapping[str, Any]) -> str:
    decision = payload.get("decision")
    return str(decision.get("status", "")) if isinstance(decision, Mapping) else ""


def create_pr_publication_handoff(
    *, repository: str, intended_base_ref: str, body_path: str | Path,
    body_binding_path: str | Path, pre_commit_finalizer_path: str | Path,
    pr_metadata_finalizer_path: str | Path, pr_metadata_guard_path: str | Path,
) -> PrPublicationHandoff:
    """Seal exact publication intent from the already-authoritative landing artifacts.

    This function has no publication or hosted-observation authority.
    """
    if not repository.strip() or not intended_base_ref.strip():
        raise ValueError("repository_and_base_ref_required")
    paths = {
        "body_binding": str(body_binding_path),
        "pre_commit_finalizer": str(pre_commit_finalizer_path),
        "pr_metadata_finalizer": str(pr_metadata_finalizer_path),
        "pr_metadata_guard": str(pr_metadata_guard_path),
    }
    body_binding = _json_object(body_binding_path, "body_binding")
    pre = _json_object(pre_commit_finalizer_path, "pre_commit_finalizer")
    post = _json_object(pr_metadata_finalizer_path, "pr_metadata_finalizer")
    guard = _json_object(pr_metadata_guard_path, "pr_metadata_guard")
    reasons: list[str] = []
    if _decision_status(pre) != "ready_to_commit": reasons.append("pre_commit_finalizer_not_ready")
    if _decision_status(post) != "ready_for_pr_metadata": reasons.append("pr_metadata_finalizer_not_ready")
    if guard.get("status") != "pr_metadata_guard_ready": reasons.append("pr_metadata_guard_not_ready")
    commit = post.get("commit_binding")
    if not isinstance(commit, Mapping):
        reasons.append("commit_binding_missing"); commit = {}
    pre_plan = pre.get("landing_validation_plan")
    post_plan = post.get("landing_validation_plan")
    plan: Mapping[str, Any]
    if not isinstance(pre_plan, Mapping) or not isinstance(post_plan, Mapping) or pre_plan != post_plan:
        reasons.append("landing_validation_plan_mismatch"); plan = {}
    else:
        plan = pre_plan
    if body_binding.get("schema_version") != SCHEMA_VERSION: reasons.append("body_binding_schema_mismatch")
    if body_binding.get("commit_sha") != commit.get("head_sha"): reasons.append("body_binding_head_mismatch")
    if body_binding.get("tree_sha") != commit.get("tree_sha"): reasons.append("body_binding_tree_mismatch")
    body = Path(body_path).read_bytes()
    if body_binding.get("body_sha256") != sha256_bytes(body): reasons.append("body_digest_mismatch")
    if body_binding.get("body_byte_length") != len(body): reasons.append("body_length_mismatch")
    guard_proof_value = guard.get("proof")
    guard_proof: Mapping[str, Any] = guard_proof_value if isinstance(guard_proof_value, Mapping) else {}
    if guard_proof.get("head_sha") and guard_proof.get("head_sha") != commit.get("head_sha"):
        reasons.append("metadata_guard_head_mismatch")
    acceptance_value = post.get("task_acceptance")
    acceptance: Mapping[str, Any] = acceptance_value if isinstance(acceptance_value, Mapping) else {}
    if acceptance and acceptance.get("status") != "task_acceptance_ready": reasons.append("task_acceptance_not_ready")
    if reasons:
        raise ValueError("publication_handoff_contradiction:" + ",".join(sorted(set(reasons))))
    payload: dict[str, Any] = {
        "schema_version": PUBLICATION_HANDOFF_SCHEMA_VERSION,
        "status": PUBLICATION_HANDOFF_READY,
        "repository": repository,
        "intended_base_ref": intended_base_ref,
        "intended_base_sha": str(commit.get("parent_sha", "")),
        "intended_head_sha": str(commit.get("head_sha", "")),
        "intended_head_tree_sha": str(commit.get("tree_sha", "")),
        "title": str(body_binding.get("title", "")),
        "body_sha256": str(body_binding.get("body_sha256", "")),
        "body_byte_length": int(body_binding.get("body_byte_length", -1)),
        "validation_profile": str(plan.get("effective_profile", "")),
        "exhaustive_matrix_status": str(plan.get("exhaustive_matrix_status", "")),
        "task_acceptance_manifest_sha256": str(acceptance.get("manifest_digest", "")),
        "task_acceptance_provenance_sha256": str(acceptance.get("provenance_digest", "")),
        "evidence_sha256": {name: file_sha256(Path(path)) for name, path in sorted(paths.items())},
        "boundary": {"publishes_pr": False, "observes_hosted_pr": False, "grants_network_authority": False},
    }
    return PrPublicationHandoff(**payload, handoff_sha256=digest_json(payload))


def verify_pr_publication_handoff(handoff: Mapping[str, Any], **inputs: Any) -> LandingEvidenceVerification:
    try:
        rebuilt = create_pr_publication_handoff(**inputs).to_dict()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return LandingEvidenceVerification("pr_publication_handoff_blocked", (str(exc),), {})
    supplied = dict(handoff)
    reasons = tuple(f"handoff_mismatch:{key}" for key in sorted(set(rebuilt) | set(supplied)) if rebuilt.get(key) != supplied.get(key))
    return LandingEvidenceVerification(PUBLICATION_HANDOFF_READY if not reasons else "pr_publication_handoff_blocked", reasons, {"handoff_sha256": rebuilt["handoff_sha256"], "body_sha256": rebuilt["body_sha256"], "body_byte_length": rebuilt["body_byte_length"]})


def create_hosted_pr_publication_custody(
    *, handoff: Mapping[str, Any], observation: Mapping[str, Any],
    hosted_body_path: str | Path | None = None, **handoff_inputs: Any,
) -> HostedPrPublicationCustody:
    """Bind externally supplied hosted state to reconstructed publication authority.

    Observation collection is deliberately outside this metadata-only function.
    """
    handoff_check = verify_pr_publication_handoff(handoff, **handoff_inputs)
    if handoff_check.status != PUBLICATION_HANDOFF_READY:
        raise ValueError("governing_handoff_not_verified:" + ",".join(handoff_check.reasons))
    expected = create_pr_publication_handoff(**handoff_inputs).to_dict()
    authorized_keys = (
        "repository", "intended_base_ref", "intended_base_sha", "intended_head_sha",
        "intended_head_tree_sha", "title", "body_sha256", "body_byte_length",
        "validation_profile", "exhaustive_matrix_status",
        "task_acceptance_manifest_sha256", "task_acceptance_provenance_sha256",
        "evidence_sha256",
    )
    authorized = {key: expected[key] for key in authorized_keys}
    observed = dict(observation)
    reasons: list[str] = []
    provenance = observed.get("provenance")
    if not isinstance(provenance, Mapping) or provenance.get("independent_hosted_observation") is not True:
        reasons.append("independent_hosted_observation_required")
    if isinstance(provenance, Mapping) and provenance.get("publication_actuator_payload_echo") is True:
        reasons.append("publication_actuator_payload_echo_untrusted")
    required = (
        "repository", "pr_number", "base_ref", "base_sha", "head_sha", "head_tree_sha",
        "title", "body_sha256", "body_byte_length", "validation_profile",
        "handoff_sha256", "merge_state",
    )
    reasons.extend(f"hosted_observation_missing:{key}" for key in required if observed.get(key) in (None, ""))
    comparisons = {
        "repository": "repository", "base_ref": "intended_base_ref",
        "base_sha": "intended_base_sha", "head_tree_sha": "intended_head_tree_sha",
        "title": "title", "body_sha256": "body_sha256",
        "body_byte_length": "body_byte_length", "validation_profile": "validation_profile",
        "handoff_sha256": "handoff_sha256",
    }
    for observed_key, expected_key in comparisons.items():
        if observed.get(observed_key) not in (None, "") and observed.get(observed_key) != expected.get(expected_key):
            reasons.append(f"hosted_publication_mismatch:{observed_key}")
    body_proof: dict[str, Any] = {"supplied": hosted_body_path is not None}
    if hosted_body_path is None:
        reasons.append("exact_hosted_body_bytes_required")
    else:
        body_bytes = Path(hosted_body_path).read_bytes()
        try:
            body_bytes.decode("utf-8")
        except UnicodeDecodeError:
            reasons.append("hosted_body_not_utf8")
        body_proof.update({"sha256": sha256_bytes(body_bytes), "byte_length": len(body_bytes)})
        if body_proof["sha256"] != expected["body_sha256"]: reasons.append("hosted_publication_mismatch:body_bytes")
        if body_proof["byte_length"] != expected["body_byte_length"]: reasons.append("hosted_publication_mismatch:body_byte_length")
        if observed.get("body_sha256") != body_proof["sha256"]: reasons.append("hosted_observation_body_digest_contradiction")
        if observed.get("body_byte_length") != body_proof["byte_length"]: reasons.append("hosted_observation_body_length_contradiction")
    merge_state = observed.get("merge_state")
    if merge_state == "merged":
        if not observed.get("merge_commit_sha"): reasons.append("hosted_observation_missing:merge_commit_sha")
        if not observed.get("merge_commit_tree_sha"): reasons.append("hosted_observation_missing:merge_commit_tree_sha")
    equivalence = {
        "head_sha_exact": observed.get("head_sha") == expected["intended_head_sha"],
        "tree_equal": observed.get("head_tree_sha") == expected["intended_head_tree_sha"],
        "parent_equal": None,
        "subject_equal": None,
    }
    if observed.get("intended_head_parent_sha") and observed.get("hosted_head_parent_sha"):
        equivalence["parent_equal"] = observed["intended_head_parent_sha"] == observed["hosted_head_parent_sha"] == expected["intended_base_sha"]
    if observed.get("intended_head_subject") and observed.get("hosted_head_subject"):
        equivalence["subject_equal"] = observed["intended_head_subject"] == observed["hosted_head_subject"]
    mismatch = any(reason.startswith("hosted_publication_mismatch:") or reason.startswith("hosted_observation_body_") for reason in reasons)
    insufficient = any(reason.startswith("hosted_observation_missing:") or reason in {
        "independent_hosted_observation_required", "publication_actuator_payload_echo_untrusted",
        "exact_hosted_body_bytes_required", "hosted_body_not_utf8",
    } for reason in reasons)
    if mismatch:
        status = HOSTED_PUBLICATION_MISMATCH
    elif insufficient:
        status = HOSTED_PUBLICATION_INSUFFICIENT
    elif not equivalence["head_sha_exact"] and equivalence["tree_equal"]:
        status = HOSTED_PUBLICATION_REWRITTEN
    elif not equivalence["head_sha_exact"]:
        status = HOSTED_PUBLICATION_MISMATCH
        reasons.append("hosted_publication_mismatch:head_sha")
    else:
        status = HOSTED_PUBLICATION_EXACT
    payload: dict[str, Any] = {
        "schema_version": HOSTED_PUBLICATION_SCHEMA_VERSION, "status": status,
        "exact_publication_custody": status == HOSTED_PUBLICATION_EXACT,
        "handoff_sha256": expected["handoff_sha256"], "authorized_publication": authorized,
        "hosted_observation": observed, "exact_hosted_body": body_proof,
        "equivalence": equivalence, "reasons": tuple(sorted(set(reasons))),
        "boundary": {"observes_network": False, "publishes_pr": False, "mutates_hosted_state": False},
    }
    return HostedPrPublicationCustody(**payload, custody_sha256=digest_json(payload))


def verify_hosted_pr_publication_custody(
    custody: Mapping[str, Any], *, handoff: Mapping[str, Any], observation: Mapping[str, Any],
    hosted_body_path: str | Path | None = None, **handoff_inputs: Any,
) -> LandingEvidenceVerification:
    try:
        rebuilt = create_hosted_pr_publication_custody(
            handoff=handoff, observation=observation, hosted_body_path=hosted_body_path,
            **handoff_inputs,
        ).to_dict()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return LandingEvidenceVerification(HOSTED_PUBLICATION_MISMATCH, (str(exc),), {})
    supplied = dict(custody)
    reasons = tuple(f"hosted_custody_artifact_mismatch:{key}" for key in sorted(set(rebuilt) | set(supplied)) if canonical_json(rebuilt.get(key)) != canonical_json(supplied.get(key)))
    status = rebuilt["status"] if not reasons else HOSTED_PUBLICATION_MISMATCH
    return LandingEvidenceVerification(status, reasons or tuple(rebuilt["reasons"]), {"custody_sha256": rebuilt["custody_sha256"], "exact_publication_custody": rebuilt["exact_publication_custody"], "equivalence": rebuilt["equivalence"]})


def classify_publication_result(observation: Mapping[str, Any], expected: Mapping[str, Any]) -> LandingEvidenceVerification:
    reasons: list[str] = []
    for key in ("repository", "base", "head_branch", "head_sha", "title"):
        if observation.get(key) and expected.get(key) and observation.get(key) != expected.get(key): reasons.append(f"publication_result_contradicted:{key}")
    if reasons: status = "publication_result_contradicted"
    elif observation.get("merged") is True: status = "publication_merge_observed"
    elif observation.get("repository") and observation.get("base") and observation.get("head_branch") and observation.get("head_sha"): status = "publication_head_binding_observed"
    elif observation.get("pr_number") and observation.get("url"): status = "publication_identifier_observed"
    else: status = "publication_payload_echo_unverified"
    return LandingEvidenceVerification(status, tuple(reasons), {"independent_remote_verification": False, "observation": dict(observation)})
