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

REQUIRED_PRS = tuple(range(1898, 1918))
CANDIDATES = (
    "Current-roadmap freshness verifier",
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
    present_1918 = "PR #1918" in text
    results.append(_check(
        "consumed_work.pr_1918_optional",
        True,
        "Roadmap mentions optional PR #1918." if present_1918 else "Roadmap does not mention optional PR #1918; this is informational when current history intentionally records through PR #1917.",
        severity="info",
    ))
    return results


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
    raw = source_bytes if source_bytes is not None else text.encode("utf-8")
    groups = {
        "consumed_work_results": _consumed_work_results(text),
        "blocked_surface_results": _blocked_surface_results(text),
        "bootstrap_contract_results": _bootstrap_contract_results(text),
        "candidate_track_results": _candidate_track_results(text),
        "forbidden_authority_results": _forbidden_authority_results(text),
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
    return verify_roadmap_text(text, str(path), source_bytes=raw)


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
    for key in ("verifier_id", "metadata_only", "verifier_only", "roadmap_path", "source_digest_algo", "source_digest", "source_byte_size"):
        sections.append(f"| {_cell(key)} | {_cell(report.get(key, ''))} |")
    sections.extend(["", "## Verification status", f"`{_cell(report.get('verification_status', ''))}`", ""])
    section_map = (
        ("Verification checks", "verification_checks"),
        ("Consumed work results", "consumed_work_results"),
        ("Blocked surface results", "blocked_surface_results"),
        ("Bootstrap contract results", "bootstrap_contract_results"),
        ("Candidate track results", "candidate_track_results"),
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
