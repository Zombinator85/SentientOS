"""Deterministic review-only repository mutation handoff artifacts.

This module never stages files, creates commits, mutates branches, pushes,
creates pull requests, invokes providers, assembles prompts, or contacts a
network.  It binds an already-approved proposal to explicit repository-relative
paths and file digests for later operator/Codex landing review.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "repository-mutation-handoff.v1"
READY = "repository_mutation_handoff_ready_for_operator_review"
BLOCKED = "repository_mutation_handoff_blocked"
INCOMPLETE = "repository_mutation_handoff_incomplete"
CONTRADICTED = "repository_mutation_handoff_contradicted"
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


def validate_approved_path(path: str) -> None:
    if not path or path in {".", "./", ""}:
        raise HandoffInputError("repository-root blanket scope is not allowed")
    pure = Path(path)
    if pure.is_absolute():
        raise HandoffInputError(f"absolute path is not allowed: {path}")
    parts = pure.parts
    if any(part == ".." for part in parts):
        raise HandoffInputError(f"path traversal is not allowed: {path}")
    if any(part == ".git" for part in parts):
        raise HandoffInputError(f".git paths are not allowed: {path}")
    if any("*" in part or "?" in part or "[" in part or "]" in part for part in parts):
        raise HandoffInputError(f"wildcard path scope is not allowed: {path}")


def _path_evidence(repo_root: Path, path: str) -> tuple[dict[str, Any], list[str], list[str]]:
    validate_approved_path(path)
    candidate = repo_root / path
    reasons: list[str] = []
    risks: list[str] = []
    exists = candidate.exists()
    regular = candidate.is_file() and not candidate.is_symlink()
    within = False
    digest = ""
    byte_count = 0
    try:
        resolved_root = repo_root.resolve(strict=True)
        resolved_candidate = candidate.resolve(strict=False)
        within = resolved_candidate == resolved_root or resolved_root in resolved_candidate.parents
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
        digest = hashlib.sha256(data).hexdigest()
        byte_count = len(data)
    return {
        "path": path,
        "sha256": digest,
        "byte_count": byte_count,
        "file_exists": exists,
        "regular_file": regular,
        "within_repository": within,
        "approved_for_review": exists and regular and within,
    }, reasons, risks


def build_repository_mutation_handoff(
    proposal: Mapping[str, Any],
    *,
    repo_root: str | Path,
    source_revision: str = "unknown",
    created_at: str = "1970-01-01T00:00:00+00:00",
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    proposal_id = _proposal_value(proposal, "proposal_id")
    status = _proposal_value(proposal, "status") or "unknown"
    ledger = _proposal_value(proposal, "ledger_entry") or _proposal_value(proposal, "ledger_reference")
    approval = _proposal_value(proposal, "approval_reference")
    paths = approved_paths_from_proposal(proposal)
    reasons: list[str] = []
    warnings: list[str] = []
    risks: list[str] = []
    if not proposal_id:
        reasons.append("missing_proposal_id")
    if status != "approved":
        reasons.append("proposal_not_approved")
    if not (ledger or approval):
        reasons.append("missing_approval_or_ledger_reference")
    if not paths:
        reasons.append("missing_explicit_approved_paths")
    if source_revision == "unknown":
        warnings.append("source_revision_unknown")

    evidence = []
    seen = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        item, item_reasons, item_risks = _path_evidence(root, path)
        evidence.append(item)
        reasons.extend(item_reasons)
        risks.extend(item_risks)
    approved_paths = tuple(sorted(seen))
    evidence = sorted(evidence, key=lambda item: str(item["path"]))

    if risks:
        handoff_status = CONTRADICTED
    elif reasons:
        handoff_status = INCOMPLETE if any(r.startswith("missing_") for r in reasons) else BLOCKED
    else:
        handoff_status = READY

    title_summary = _proposal_value(proposal, "summary") or proposal_id or "repository mutation handoff"
    base: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "handoff_status": handoff_status,
        "proposal_id": proposal_id,
        "proposal_status": status,
        "approval_reference": approval,
        "ledger_reference": ledger,
        "repository_root": str(root),
        "source_revision": source_revision,
        "approved_paths": list(approved_paths),
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
    handoff_id_payload = {k: v for k, v in base.items() if k not in {"created_at"}}
    base["handoff_id"] = f"repository_mutation_handoff:{_digest_payload(handoff_id_payload)[:24]}"
    digest_payload = dict(base)
    digest_payload["digest"] = ""
    base["digest"] = _digest_payload(digest_payload)
    return base


def write_handoff_json(handoff: Mapping[str, Any], output: str | Path) -> None:
    Path(output).write_text(json.dumps(handoff, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def render_handoff_markdown(handoff: Mapping[str, Any]) -> str:
    def esc(value: object) -> str:
        return str(value).replace("|", "\\|").replace("\n", "<br>")
    lines = [
        "# Repository Mutation Handoff",
        "",
        f"- Status: `{esc(handoff.get('handoff_status'))}`",
        f"- Proposal: `{esc(handoff.get('proposal_id'))}`",
        f"- Metadata only: `{esc(handoff.get('metadata_only'))}`",
        f"- Repository mutation authorized: `{esc(handoff.get('repository_mutation_authorized'))}`",
        "",
        "| Path | SHA-256 | Bytes | Exists | Regular | Within repository | Approved for review |",
        "| --- | --- | ---: | --- | --- | --- | --- |",
    ]
    for item in handoff.get("approved_path_evidence", []):
        if isinstance(item, Mapping):
            lines.append("| " + " | ".join(esc(item.get(k, "")) for k in ("path", "sha256", "byte_count", "file_exists", "regular_file", "within_repository", "approved_for_review")) + " |")
    lines.append("")
    return "\n".join(lines)


def is_ready_handoff(handoff: Mapping[str, Any]) -> bool:
    return handoff.get("handoff_status") == READY and all(handoff.get(flag) is False for flag in _FALSE_FLAGS)
