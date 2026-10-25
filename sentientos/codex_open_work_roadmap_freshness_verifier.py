from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

VERIFIER_ID = "codex_open_work_roadmap_freshness_verifier.v1"
VERIFIED = "codex_open_work_roadmap_freshness_verified"
FAILED = "codex_open_work_roadmap_freshness_failed"
DEFAULT_ROADMAP_PATH = Path("docs/development/codex_open_work_roadmap_index.md")
AUTHORITY_BOUNDARY = "metadata-only roadmap freshness evidence; no implementation, runtime, readiness, commit, or PR authority"
NON_AUTHORITY_POSTURE = (
    "Verifier success is only roadmap freshness evidence. It is not implementation selection, "
    "runtime authority, consent, policy truth, prompt assembly, prompt export, provider invocation, "
    "network authority, live-memory mutation, host action, ledger authority, glow authority, daemon "
    "authority, scheduler authority, model-training authority, federation authority, commit authority, "
    "PR authority, or readiness authority."
)

REQUIRED_PRS = tuple(range(1898, 1923))
CANDIDATES = (
    "Consent-ladder index/readability consolidation",
    "Next-selection packet template",
)
FORBIDDEN_SURFACES = (
    "runtime authority",
    "live-memory mutation",
    "provider invocation",
    "network calls",
    "prompt export",
    "host action",
    "ledger writes",
    "glow archives",
    "daemon action",
    "scheduler behavior",
    "model training",
    "federation authority",
    "autonomous repository staging",
    "autonomous repository mutation",
    "repository staging",
    "committing",
    "commit authority",
    "branch mutation",
    "pushing",
    "PR creation",
    "repository authority",
    "runtime proposal adoption",
    "sandboxed readiness gate",
    "sandboxed readiness packet",
    "sandboxed readiness envelope",
    "post-envelope sandboxed adapter continuation",
)
POSITIVE_AUTHORIZATION = (
    "authorizes", "authorize", "grants", "grant", "allows", "allow", "enables", "enable",
    "implements", "implement", "opens", "open", "selects", "select", "activates", "activate",
)
DENIAL_MARKERS = (
    "must not", "does not", "do not", "not authorized", "blocked", "forbidden", "without authority",
    "requires separate authorization", "never authorize", "not grant", "cannot", "no ", "non-authority",
    "it is not", "not consent", "must not be reopened",
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _check(check_id: str, passed: bool, details: str, *, severity: str | None = None) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "passed": passed,
        "severity": severity or ("info" if passed else "violation"),
        "details": details,
        "authority_boundary": AUTHORITY_BOUNDARY,
    }


def _contains_all(text: str, terms: Sequence[str]) -> bool:
    norm = _norm(text)
    return all(term.lower() in norm for term in terms)


def _consumed_work_results(text: str) -> list[dict[str, Any]]:
    results = []
    for pr in REQUIRED_PRS:
        marker = f"PR #{pr}"
        results.append(_check(f"consumed_work.pr_{pr}", marker in text, f"Roadmap mentions {marker}."))
    sequence_specs = (
        ("consumed_work.roadmap_refresh_sequence", ("PR #1918", "refreshed", "roadmap")),
        ("consumed_work.freshness_verifier_consumed", ("PR #1919", "current-roadmap freshness verifier", "already implemented", "metadata-only review/test tooling")),
        ("consumed_work.repository_mutation_custody_1920", ("PR #1920", "repository mutation custody", "external", "review handoff")),
        ("consumed_work.repository_mutation_custody_1921", ("PR #1921", "approval-time digest", "revision binding", "external handoff storage", "immutable payload verification")),
        ("consumed_work.repository_mutation_custody_1922", ("PR #1922", "canonical path/digest invariants", "semantic readiness verification", "canonical-duplicate contradictions", "ledger-or-approval selection")),
    )
    for cid, terms in sequence_specs:
        results.append(_check(cid, _contains_all(text, terms), f"Required consumed-sequence wording preserved: {', '.join(terms)}."))
    return results



def _repository_mutation_custody_results(text: str) -> list[dict[str, Any]]:
    specs = (
        ("repository_mutation_custody.consumed_through_1922", ("repository-mutation custody through PR #1922", "review evidence only")),
        ("repository_mutation_custody.autonomous_mutation_blocked", ("must not authorize autonomous repository mutation", "staging", "committing", "branch mutation", "pushing", "PR creation")),
        ("repository_mutation_custody.handoff_readiness_non_authority", ("handoff readiness remains non-authority",)),
        ("repository_mutation_custody.external_landing_controls_required", ("external Codex/operator landing controls remain required",)),
        ("repository_mutation_custody.no_runtime_proposal_adoption", ("runtime proposal adoption", "must not")),
        ("repository_mutation_custody.no_evidence_to_authority", ("evidence-to-authority escalation", "must not")),
    )
    return [_check(cid, _contains_all(text, terms), f"Required repository-mutation custody wording preserved: {', '.join(terms)}.") for cid, terms in specs]

def _blocked_surface_results(text: str) -> list[dict[str, Any]]:
    specs = (
        ("blocked_surface.terminal_envelope", ("sandboxed_live_memory_commit_adapter_envelope", "terminal")),
        ("blocked_surface.no_post_envelope", ("no post-envelope implementation",)),
        ("blocked_surface.no_readiness_gate", ("sandboxed readiness gate",)),
        ("blocked_surface.no_readiness_packet", ("readiness packet",)),
        ("blocked_surface.no_readiness_envelope", ("readiness envelope",)),
        ("blocked_surface.no_repeated_ladder", ("repeated sandboxed", "ladder")),
        ("blocked_surface.topology_decision_required", ("complete topology decision",)),
        ("blocked_surface.metadata_not_live_authority", ("metadata", "review evidence", "not", "live", "authority")),
    )
    return [_check(cid, _contains_all(text, terms), f"Required blocked-surface wording preserved: {', '.join(terms)}.") for cid, terms in specs]


def _bootstrap_contract_results(text: str) -> list[dict[str, Any]]:
    specs = (
        ("bootstrap_contract.link", ("codex_bootstrap_invocation_contract.md",)),
        ("bootstrap_contract.supported_flags", ("supported bootstrap flags",)),
        ("bootstrap_contract.unsupported_existing_module", ("--existing-module",)),
        ("bootstrap_contract.unsupported_existing_cli", ("--existing-cli",)),
        ("bootstrap_contract.stop_retry_nonzero", ("argument parsing exits nonzero",)),
    )
    return [_check(cid, _contains_all(text, terms), f"Required bootstrap-contract wording preserved: {', '.join(terms)}.") for cid, terms in specs]


def _candidate_section(text: str) -> str:
    match = re.search(r"## Candidate next work tracks(?P<body>.*?)(?:\n## |\Z)", text, flags=re.S)
    return match.group("body") if match else ""


def _candidate_track_results(text: str) -> list[dict[str, Any]]:
    section = _candidate_section(text)
    results: list[dict[str, Any]] = []
    for candidate in CANDIDATES:
        count = section.count(f"| {candidate} |")
        results.append(_check(f"candidate_track.{candidate.lower().replace(' ', '_').replace('/', '_').replace('-', '_')}", count == 1, f"Candidate appears exactly once in candidate table; count={count}."))
    extra_rows = [line for line in section.splitlines() if line.startswith("| ") and not line.startswith("| ---") and "Candidate option" not in line]
    names = [row.split("|")[1].strip() for row in extra_rows if len(row.split("|")) > 2]
    results.append(_check("candidate_track.exact_candidate_set", tuple(names) == CANDIDATES, f"Candidate set is {names}."))
    posture_specs = (
        ("candidate_track.documentation_review_test_only", ("documentation/review/test-only",)),
        ("candidate_track.separate_operator_selection", ("requires separate operator selection",)),
        ("candidate_track.no_implementation_authority", ("does not authorize implementation",)),
        ("candidate_track.no_runtime_authority_grant", ("does not grant runtime", "live-memory mutation", "provider invocation", "network call", "prompt export", "host action", "ledger write", "glow archive", "daemon action", "scheduler behavior", "model training", "federation authority")),
    )
    for cid, terms in posture_specs:
        results.append(_check(cid, _contains_all(section, terms), f"Candidate non-authority posture preserved: {', '.join(terms)}."))
    return results


def _active_next_work_results(text: str) -> list[dict[str, Any]]:
    match = re.search(r"## Available next work(?P<body>.*?)(?:\n## |\Z)", text, flags=re.S)
    body = match.group("body") if match else ""
    candidates = [line[2:].strip() for line in body.splitlines() if line.startswith("- ")]
    expected = (
        "Documentation/readability consolidation that removes duplication without weakening canonical controls.",
        "Developer-workflow proof hardening grounded in an observed mechanical gap.",
        "A separately researched and operator-selected bounded subsystem with explicit authority boundaries and observable acceptance proof.",
    )
    results = [
        _check(
            "candidate_track.active_available_next_work",
            tuple(candidates) == expected,
            f"Active next-work options match the canonical set; candidates={candidates}.",
        ),
        _check(
            "candidate_track.active_selection_remains_external",
            "operator-named target" in _norm(text)
            and "separately selected safe candidate" in _norm(text)
            and "must pass clean fresh-current and bootstrap gates" in _norm(text),
            "Active options preserve separate operator selection and fresh-current/bootstrap gates.",
        ),
        _check(
            "candidate_track.active_non_authority",
            "does not authorize implementation" not in _norm(body)
            and "no implementation authority" not in _norm(body)
            and "no runtime authority" not in _norm(body)
            and "must preserve all root authority boundaries" in _norm(text),
            "Active options remain bounded by root authority boundaries.",
        ),
    ]
    return results


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def _is_denial(sentence: str) -> bool:
    lower = _norm(sentence)
    return any(marker in lower for marker in DENIAL_MARKERS)


def _forbidden_authority_results(text: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    sentences = _sentences(text)
    for surface in FORBIDDEN_SURFACES:
        bad: list[str] = []
        surface_norm = surface.lower()
        for sentence in sentences:
            lower = _norm(sentence)
            has_positive_verb = any(re.search(r"\b" + re.escape(verb) + r"\b", lower) for verb in POSITIVE_AUTHORIZATION)
            if surface_norm in lower and has_positive_verb and not _is_denial(sentence):
                bad.append(sentence)
        findings.append(_check(
            "forbidden_authority." + surface.replace("-", "_").replace(" ", "_"),
            not bad,
            "No positive authorization language detected." if not bad else "Positive authorization drift detected: " + " | ".join(bad),
        ))
    return findings


def verify_roadmap_text(text: str, roadmap_path: str, *, source_bytes: bytes | None = None) -> dict[str, Any]:
    return _verify_roadmap_text(
        text,
        roadmap_path,
        source_bytes=source_bytes,
        history_text=None,
        candidate_text=text,
    )


def _verify_roadmap_text(
    text: str,
    roadmap_path: str,
    *,
    source_bytes: bytes | None,
    history_text: str | None,
    candidate_text: str,
) -> dict[str, Any]:
    raw = source_bytes if source_bytes is not None else text.encode("utf-8")
    freshness_text = text if history_text is None else f"{text}\n{history_text}"
    groups = {
        "consumed_work_results": _consumed_work_results(freshness_text),
        "blocked_surface_results": _blocked_surface_results(freshness_text),
        "bootstrap_contract_results": _bootstrap_contract_results(freshness_text),
        "candidate_track_results": (
            _active_next_work_results(candidate_text)
            if history_text is not None
            else _candidate_track_results(candidate_text)
        ),
        "repository_mutation_custody_results": _repository_mutation_custody_results(freshness_text),
        "forbidden_authority_results": _forbidden_authority_results(freshness_text),
    }
    checks = [check for values in groups.values() for check in values]
    violations = [check for check in checks if not check["passed"] and check["severity"] == "violation"]
    return {
        "verifier_id": VERIFIER_ID,
        "metadata_only": True,
        "verifier_only": True,
        "roadmap_path": roadmap_path,
        "source_digest_algo": "sha256",
        "source_digest": hashlib.sha256(raw).hexdigest(),
        "source_byte_size": len(raw),
        "verification_status": VERIFIED if not violations else FAILED,
        "verification_checks": checks,
        **groups,
        "violation_summary": {
            "violation_count": len(violations),
            "violation_check_ids": [str(check["check_id"]) for check in violations],
        },
        "non_authority_posture": NON_AUTHORITY_POSTURE,
    }


def verify_roadmap_file(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if not raw:
        raise ValueError("roadmap file is empty")
    text = raw.decode("utf-8")
    if not text.strip():
        raise ValueError("roadmap file is empty")
    archive_links = re.findall(r"\]\(([^)#]*codex_open_work_roadmap_archive_[^/)]+\.md)\)", text)
    if not archive_links and path.name != DEFAULT_ROADMAP_PATH.name:
        return verify_roadmap_text(text, str(path), source_bytes=raw)
    if len(archive_links) != 1:
        raise ValueError("active roadmap must declare exactly one consumed-history archive")
    archive_path = (path.parent / archive_links[0]).resolve()
    if archive_path.parent != path.parent.resolve():
        raise ValueError("roadmap archive must be a sibling file")
    archive_raw = archive_path.read_bytes()
    if not archive_raw:
        raise ValueError("roadmap archive file is empty")
    archive_text = archive_raw.decode("utf-8")
    if not archive_text.strip():
        raise ValueError("roadmap archive file is empty")
    source_manifest = json.dumps(
        {
            "active_index": {"path": path.name, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)},
            "consumed_history_archive": {
                "path": archive_path.name,
                "sha256": hashlib.sha256(archive_raw).hexdigest(),
                "bytes": len(archive_raw),
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    report = _verify_roadmap_text(
        text,
        str(path),
        source_bytes=source_manifest,
        history_text=archive_text,
        candidate_text=text,
    )
    report["source_digest_algo"] = "sha256-canonical-input-manifest"
    report["source_byte_size"] = len(source_manifest)
    report["source_inputs"] = json.loads(source_manifest)
    return report


def dumps_report(report: Mapping[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def _cell(value: object) -> str:
    text = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
    return text.replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>")


def _checks_table(checks: Sequence[Mapping[str, Any]]) -> list[str]:
    lines = ["| Check ID | Passed | Severity | Details | Authority boundary |", "| --- | --- | --- | --- | --- |"]
    for check in checks:
        lines.append("| " + " | ".join(_cell(check[key]) for key in ("check_id", "passed", "severity", "details", "authority_boundary")) + " |")
    return lines


def render_markdown(report: Mapping[str, Any]) -> str:
    sections: list[str] = [
        "# Codex Open-Work Roadmap Freshness Verification",
        "",
        "## Source summary",
        "| Field | Value |",
        "| --- | --- |",
    ]
    source_summary_keys = [
        "verifier_id", "metadata_only", "verifier_only", "roadmap_path",
        "source_digest_algo", "source_digest", "source_byte_size",
    ]
    if "source_inputs" in report:
        source_summary_keys.append("source_inputs")
    for key in source_summary_keys:
        sections.append(f"| {_cell(key)} | {_cell(report.get(key, ''))} |")
    sections.extend(["", "## Verification status", f"`{_cell(report.get('verification_status', ''))}`", ""])
    section_map = (
        ("Verification checks", "verification_checks"),
        ("Consumed work results", "consumed_work_results"),
        ("Blocked surface results", "blocked_surface_results"),
        ("Bootstrap contract results", "bootstrap_contract_results"),
        ("Candidate track results", "candidate_track_results"),
        ("Repository mutation custody results", "repository_mutation_custody_results"),
        ("Forbidden authority results", "forbidden_authority_results"),
    )
    for title, key in section_map:
        sections.extend([f"## {title}", *_checks_table(report.get(key, [])), ""])
    sections.extend([
        "## Violation summary",
        "| Field | Value |",
        "| --- | --- |",
    ])
    summary = report.get("violation_summary", {})
    if isinstance(summary, Mapping):
        for key in sorted(summary):
            sections.append(f"| {_cell(key)} | {_cell(summary[key])} |")
    sections.extend(["", "## Non-authority posture", _cell(report.get("non_authority_posture", NON_AUTHORITY_POSTURE)), ""])
    return "\n".join(sections)
