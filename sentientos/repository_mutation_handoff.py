"""Deterministic review-only repository mutation handoff artifacts.

This module never stages files, creates commits, mutates branches, pushes,
creates pull requests, invokes providers, assembles prompts, or contacts a
network. It binds an already-approved proposal to approval-time file digests
and a known source revision for later operator/Codex landing review.
"""
from __future__ import annotations

import hashlib
import json
import os
import posixpath
import platform
import subprocess
import tempfile
import contextlib
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "repository-mutation-handoff.v2"
READY = "repository_mutation_handoff_ready_for_operator_review"
BLOCKED = "repository_mutation_handoff_blocked"
INCOMPLETE = "repository_mutation_handoff_incomplete"
CONTRADICTED = "repository_mutation_handoff_contradicted"
UNKNOWN_REVISION = "unknown"
_FALSE_FLAGS = {
    "repository_mutation_authorized": False,
    "staging_performed": False,
    "commit_performed": False,
    "branch_mutation_performed": False,
    "push_performed": False,
    "pull_request_created": False,
    "network_performed": False,
    "provider_invocation_performed": False,
    "prompt_assembly_performed": False,
    "runtime_authority_expanded": False,
}

class HandoffInputError(ValueError):
    """Raised when handoff input is malformed or path scope is unsafe."""


def _stable_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest_payload(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def _proposal_value(proposal: Mapping[str, Any], key: str) -> str:
    value = proposal.get(key)
    return str(value).strip() if value is not None else ""


def approved_paths_from_proposal(proposal: Mapping[str, Any]) -> tuple[str, ...]:
    candidates = proposal.get("approved_paths")
    if candidates is None:
        context = proposal.get("context")
        if isinstance(context, Mapping):
            candidates = context.get("approved_paths")
    if candidates is None:
        deltas = proposal.get("deltas")
        if isinstance(deltas, Mapping):
            candidates = deltas.get("approved_paths")
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        return ()
    return tuple(str(item).strip() for item in candidates if str(item).strip())


def approved_path_digests_from_proposal(proposal: Mapping[str, Any]) -> dict[str, str] | None:
    candidates: object = proposal.get("approved_path_digests")
    if candidates is None:
        context = proposal.get("context")
        if isinstance(context, Mapping):
            candidates = context.get("approved_path_digests")
    if candidates is None:
        return None
    if not isinstance(candidates, Mapping):
        raise HandoffInputError("approved_path_digests must be a mapping")
    return {str(k).strip(): str(v).strip() for k, v in candidates.items()}


def validate_approved_path(path: str) -> str:
    """Return the single lexical repository-relative spelling for an approved path."""
    raw = str(path).strip().replace("\\", "/")
    if not raw or raw in {".", "./", ""}:
        raise HandoffInputError("repository-root blanket scope is not allowed")
    pure = Path(raw)
    if pure.is_absolute() or raw.startswith("/"):
        raise HandoffInputError(f"absolute path is not allowed: {path}")
    raw_parts = tuple(part for part in raw.split("/") if part)
    if any(part == ".." for part in raw_parts):
        raise HandoffInputError(f"path traversal is not allowed: {path}")
    canonical = posixpath.normpath(raw)
    if canonical in {".", "", "./"}:
        raise HandoffInputError("repository-root blanket scope is not allowed")
    parts = tuple(part for part in canonical.split("/") if part)
    if any(part == ".." for part in parts):
        raise HandoffInputError(f"path traversal is not allowed: {path}")
    if any(part == ".git" for part in parts):
        raise HandoffInputError(f".git paths are not allowed: {path}")
    if any("*" in part or "?" in part or "[" in part or "]" in part for part in parts):
        raise HandoffInputError(f"wildcard path scope is not allowed: {path}")
    return "/".join(parts)


def _valid_sha256(value: str) -> bool:
    return len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)


def resolve_observed_source_revision(repo_root: str | Path) -> tuple[str, list[str]]:
    """Read-only source revision resolver; only runs ``git rev-parse HEAD``."""
    try:
        result = subprocess.run(("git", "rev-parse", "HEAD"), cwd=Path(repo_root), capture_output=True, text=True, check=False)
    except OSError:
        return UNKNOWN_REVISION, ["observed_source_revision_unknown"]
    revision = result.stdout.strip()
    if result.returncode == 0 and revision:
        return revision, []
    return UNKNOWN_REVISION, ["observed_source_revision_unknown"]


def resolve_runtime_handoff_root(repo_root: str | Path, explicit_root: str | Path | None = None) -> Path:
    resolved_repo = Path(repo_root).resolve()
    if explicit_root is not None:
        root = Path(explicit_root)
    elif os.getenv("SENTIENTOS_REPOSITORY_MUTATION_HANDOFF_ROOT"):
        root = Path(os.environ["SENTIENTOS_REPOSITORY_MUTATION_HANDOFF_ROOT"])
    elif platform.system().lower().startswith("win") and os.getenv("LOCALAPPDATA"):
        root = Path(os.environ["LOCALAPPDATA"]) / "SentientOS" / "repository_mutation_handoffs"
    elif os.getenv("XDG_STATE_HOME"):
        root = Path(os.environ["XDG_STATE_HOME"]) / "sentientos" / "repository_mutation_handoffs"
    else:
        root = Path.home() / ".local" / "state" / "sentientos" / "repository_mutation_handoffs"
    resolved = root.expanduser().resolve()
    git_root = resolved_repo / ".git"
    if resolved == resolved_repo or resolved_repo in resolved.parents:
        raise HandoffInputError("repository mutation handoff root must be outside the repository worktree")
    if resolved == git_root or git_root in resolved.parents:
        raise HandoffInputError("repository mutation handoff root must not be inside .git")
    return resolved


def _path_evidence(repo_root: Path, path: str, expected_sha256: str) -> tuple[dict[str, Any], list[str], list[str]]:
    canonical = validate_approved_path(path)
    candidate = repo_root / canonical
    reasons: list[str] = []
    risks: list[str] = []
    exists = candidate.exists()
    regular = candidate.is_file() and not candidate.is_symlink()
    within = False
    observed = ""
    byte_count = 0
    try:
        resolved_root = repo_root.resolve(strict=True)
        resolved_candidate = candidate.resolve(strict=False)
        within = resolved_candidate != resolved_root and resolved_root in resolved_candidate.parents
    except OSError:
        within = False
    if not exists:
        reasons.append("approved_path_missing")
    if exists and not regular:
        reasons.append("approved_path_not_regular_file")
    if not within:
        risks.append("approved_path_outside_repository")
    if exists and regular and within:
        data = candidate.read_bytes()
        observed = hashlib.sha256(data).hexdigest()
        byte_count = len(data)
    matches = bool(expected_sha256 and observed and expected_sha256 == observed)
    if expected_sha256 and observed and not matches:
        risks.append("approved_path_digest_mismatch")
    return {
        "path": canonical,
        "expected_sha256": expected_sha256,
        "observed_sha256": observed,
        "digest_matches_approval": matches,
        "byte_count": byte_count,
        "file_exists": exists,
        "regular_file": regular,
        "within_repository": within,
        "approved_for_review": exists and regular and within and matches,
    }, reasons, risks


def build_repository_mutation_handoff(
    proposal: Mapping[str, Any], *, repo_root: str | Path, source_revision: str | None = None,
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    proposal_id = _proposal_value(proposal, "proposal_id")
    status = _proposal_value(proposal, "status") or "unknown"
    ledger = _proposal_value(proposal, "ledger_entry") or _proposal_value(proposal, "ledger_reference")
    approval = _proposal_value(proposal, "approval_reference")
    paths_raw = approved_paths_from_proposal(proposal)
    digests_raw = approved_path_digests_from_proposal(proposal)
    approved_source_revision = _proposal_value(proposal, "approved_source_revision")
    observed_source_revision = (source_revision if source_revision is not None else UNKNOWN_REVISION).strip() or UNKNOWN_REVISION
    reasons: list[str] = []
    warnings: list[str] = []
    risks: list[str] = []
    if not proposal_id:
        reasons.append("missing_proposal_id")
    if status != "approved":
        reasons.append("proposal_not_approved")
    if not (ledger or approval):
        reasons.append("missing_approval_or_ledger_reference")
    if not paths_raw:
        reasons.append("missing_explicit_approved_paths")
    if digests_raw is None:
        reasons.append("missing_approved_path_digests")
        digests_raw = {}
    if not approved_source_revision or approved_source_revision == UNKNOWN_REVISION:
        reasons.append("missing_approved_source_revision")
    if not observed_source_revision or observed_source_revision == UNKNOWN_REVISION:
        reasons.append("missing_observed_source_revision")
        warnings.append("observed_source_revision_unknown")
    elif approved_source_revision and approved_source_revision != observed_source_revision:
        risks.append("source_revision_mismatch")

    canonical_paths: list[str] = []
    seen_paths: set[str] = set()
    for path in paths_raw:
        canonical = validate_approved_path(path)
        if canonical in seen_paths:
            risks.append("duplicate_canonical_approved_path")
        seen_paths.add(canonical)
        canonical_paths.append(canonical)

    canonical_digests: dict[str, str] = {}
    for path, digest in digests_raw.items():
        canonical = validate_approved_path(path)
        if not _valid_sha256(digest):
            risks.append("invalid_approved_path_digest")
        if canonical in canonical_digests:
            risks.append("duplicate_canonical_approved_path_digest_key")
            if canonical_digests[canonical] != digest:
                risks.append("conflicting_canonical_approved_path_digest")
        else:
            canonical_digests[canonical] = digest

    path_set = set(canonical_paths)
    digest_keys = set(canonical_digests)
    if digests_raw and path_set != digest_keys:
        risks.append("approved_path_digest_set_mismatch")

    evidence: list[dict[str, Any]] = []
    for path in sorted(path_set):
        item, item_reasons, item_risks = _path_evidence(root, path, canonical_digests.get(path, ""))
        evidence.append(item)
        reasons.extend(item_reasons)
        risks.extend(item_risks)
    evidence_paths = [str(item.get("path", "")) for item in evidence]
    if len(evidence_paths) != len(path_set) or set(evidence_paths) != path_set:
        risks.append("approved_path_evidence_set_mismatch")
    if any(not item.get("digest_matches_approval") or not item.get("approved_for_review") for item in evidence):
        if any(item.get("expected_sha256") and item.get("observed_sha256") and not item.get("digest_matches_approval") for item in evidence):
            risks.append("approved_path_digest_mismatch")
        elif any(not item.get("approved_for_review") for item in evidence):
            reasons.append("approved_path_not_approved_for_review")

    source_matches = bool(approved_source_revision and observed_source_revision != UNKNOWN_REVISION and approved_source_revision == observed_source_revision)
    if risks:
        handoff_status = CONTRADICTED
    elif reasons:
        handoff_status = INCOMPLETE
    else:
        handoff_status = READY
    title_summary = _proposal_value(proposal, "summary") or proposal_id or "repository mutation handoff"
    base: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "digest_algo": "sha256",
        "handoff_status": handoff_status,
        "proposal_id": proposal_id,
        "proposal_status": status,
        "approval_reference": approval,
        "ledger_reference": ledger,
        "repository_root": str(root),
        "approved_source_revision": approved_source_revision,
        "observed_source_revision": observed_source_revision,
        "source_revision_matches_approval": source_matches,
        "approved_paths": sorted(path_set),
        "approved_path_digests": {k: canonical_digests[k] for k in sorted(digest_keys)},
        "approved_path_evidence": evidence,
        "suggested_branch_name": f"codex/repository-mutation-handoff-{proposal_id or 'unknown'}",
        "suggested_commit_title": f"[codex:sentientos] review repository mutation handoff {proposal_id or 'unknown'}: {title_summary}",
        "reason_codes": sorted(set(reasons)),
        "warning_codes": sorted(set(warnings)),
        "risk_codes": sorted(set(risks)),
        "created_at": created_at,
        "metadata_only": True,
        "operator_review_required": True,
        "codex_landing_required": True,
        **_FALSE_FLAGS,
    }
    id_payload = dict(base)
    base["handoff_id"] = f"repository_mutation_handoff:{_digest_payload(id_payload)[:24]}"
    base["digest"] = ""
    base["digest"] = _digest_payload(base)
    return base

def verify_repository_mutation_handoff_digest(handoff: Mapping[str, Any]) -> bool:
    if handoff.get("digest_algo") != "sha256":
        return False
    digest = handoff.get("digest")
    if not isinstance(digest, str) or not _valid_sha256(digest):
        return False
    payload = dict(handoff)
    payload["digest"] = ""
    return _digest_payload(payload) == digest


def write_handoff_json(handoff: Mapping[str, Any], output: str | Path) -> None:
    if not verify_repository_mutation_handoff_digest(handoff):
        raise HandoffInputError("repository mutation handoff digest verification failed")
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{output_path.name}.", suffix=".tmp", dir=str(output_path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(handoff, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        Path(tmp_name).replace(output_path)
    except Exception:
        with contextlib.suppress(OSError):
            Path(tmp_name).unlink()
        raise


def render_handoff_markdown(handoff: Mapping[str, Any]) -> str:
    def esc(value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", "<br>")
    lines = [
        "# Repository Mutation Handoff",
        "",
        f"- Schema: `{esc(handoff.get('schema_version'))}`",
        f"- Status: `{esc(handoff.get('handoff_status'))}`",
        f"- Proposal: `{esc(handoff.get('proposal_id'))}`",
        f"- Approved source revision: `{esc(handoff.get('approved_source_revision'))}`",
        f"- Observed source revision: `{esc(handoff.get('observed_source_revision'))}`",
        f"- Metadata only: `{esc(handoff.get('metadata_only'))}`",
        f"- Repository mutation authorized: `{esc(handoff.get('repository_mutation_authorized'))}`",
        "",
        "| Path | Expected SHA-256 | Observed SHA-256 | Match | Bytes | Exists | Regular | Within repository | Approved for review |",
        "| --- | --- | --- | --- | ---: | --- | --- | --- | --- |",
    ]
    for item in handoff.get("approved_path_evidence", []):
        if isinstance(item, Mapping):
            lines.append("| " + " | ".join(esc(item.get(k, "")) for k in ("path", "expected_sha256", "observed_sha256", "digest_matches_approval", "byte_count", "file_exists", "regular_file", "within_repository", "approved_for_review")) + " |")
    lines.append("")
    return "\n".join(lines)


def is_ready_handoff(handoff: Mapping[str, Any]) -> bool:
    if handoff.get("schema_version") != SCHEMA_VERSION or handoff.get("digest_algo") != "sha256":
        return False
    if handoff.get("handoff_status") != READY or not verify_repository_mutation_handoff_digest(handoff):
        return False
    if handoff.get("metadata_only") is not True or handoff.get("operator_review_required") is not True or handoff.get("codex_landing_required") is not True:
        return False
    if any(handoff.get(flag) is not False for flag in _FALSE_FLAGS):
        return False
    if handoff.get("reason_codes") not in ([], ()) or handoff.get("risk_codes") not in ([], ()):
        return False
    approved_revision = handoff.get("approved_source_revision")
    observed_revision = handoff.get("observed_source_revision")
    if not isinstance(approved_revision, str) or not approved_revision or approved_revision == UNKNOWN_REVISION:
        return False
    if not isinstance(observed_revision, str) or not observed_revision or observed_revision == UNKNOWN_REVISION:
        return False
    if handoff.get("source_revision_matches_approval") is not True or approved_revision != observed_revision:
        return False
    approved_paths = handoff.get("approved_paths")
    if not isinstance(approved_paths, list) or not approved_paths:
        return False
    try:
        canonical_paths = [validate_approved_path(str(path)) for path in approved_paths]
    except HandoffInputError:
        return False
    if canonical_paths != approved_paths or canonical_paths != sorted(canonical_paths) or len(set(canonical_paths)) != len(canonical_paths):
        return False
    digests = handoff.get("approved_path_digests")
    if not isinstance(digests, Mapping):
        return False
    try:
        canonical_digests = {validate_approved_path(str(path)): str(digest) for path, digest in digests.items()}
    except HandoffInputError:
        return False
    if set(canonical_digests) != set(canonical_paths) or len(canonical_digests) != len(digests):
        return False
    if any(path != validate_approved_path(path) for path in digests.keys()):
        return False
    if any(not _valid_sha256(digest) for digest in canonical_digests.values()):
        return False
    evidence = handoff.get("approved_path_evidence")
    if not isinstance(evidence, list) or len(evidence) != len(canonical_paths):
        return False
    evidence_paths: list[str] = []
    for row in evidence:
        if not isinstance(row, Mapping):
            return False
        try:
            path = validate_approved_path(str(row.get("path", "")))
        except HandoffInputError:
            return False
        if path != row.get("path"):
            return False
        evidence_paths.append(path)
        expected = row.get("expected_sha256")
        observed = row.get("observed_sha256")
        if expected != canonical_digests.get(path):
            return False
        if not isinstance(observed, str) or not _valid_sha256(observed):
            return False
        if row.get("digest_matches_approval") is not True or row.get("approved_for_review") is not True:
            return False
        if row.get("file_exists") is not True or row.get("regular_file") is not True or row.get("within_repository") is not True:
            return False
    return evidence_paths == canonical_paths and len(set(evidence_paths)) == len(evidence_paths)
