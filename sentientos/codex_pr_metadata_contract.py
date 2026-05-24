from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
import json
import re

TITLE_RE = re.compile(r"^\[codex:[a-z0-9_\-]+\] .+")
REQUIRED_BODY_MARKERS = (
    "full command matrix results",
    "matrix runner --summary result",
    "matrix runner --output result/path",
    "targeted mypy result",
    "baseline result",
    "docs build result",
    "prompt-boundary result",
    "strict audit result",
    "immutability verifier result",
    "unresolved risks",
)
FORBIDDEN_LOCAL_ONLY_MARKERS = (
    "local tests only",
    "touched tests only",
    "only touched tests",
)


def _norm(text: str) -> str:
    return " ".join(text.lower().replace("_", " ").split())


@dataclass(frozen=True)
class CodexPRMetadataVerification:
    status: str
    title_ok: bool
    intended_commit_title_ok: bool
    missing_body_markers: tuple[str, ...]
    local_only_validation_claim_detected: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CodexPRValidationRollup:
    full_command_matrix_results: str
    matrix_runner_summary_result: str
    matrix_runner_output_result_path: str
    targeted_mypy_result: str
    baseline_result: str
    docs_build_result: str
    prompt_boundary_result: str
    strict_audit_result: str
    immutability_verifier_result: str
    unresolved_risks: str

    def build_body(self) -> str:
        sections = (
            ("Full command matrix results", self.full_command_matrix_results),
            ("Matrix runner --summary result", self.matrix_runner_summary_result),
            ("Matrix runner --output result/path", self.matrix_runner_output_result_path),
            ("Targeted mypy result", self.targeted_mypy_result),
            ("Baseline result", self.baseline_result),
            ("Docs build result", self.docs_build_result),
            ("Prompt-boundary result", self.prompt_boundary_result),
            ("Strict audit result", self.strict_audit_result),
            ("Immutability verifier result", self.immutability_verifier_result),
            ("Unresolved risks", self.unresolved_risks),
        )
        return "\n\n".join(f"## {title}\n{body.strip()}" for title, body in sections)


def build_pr_body_from_rollup(rollup: CodexPRValidationRollup) -> str:
    return rollup.build_body()


def parse_rollup_json(payload: dict[str, Any]) -> CodexPRValidationRollup:
    return CodexPRValidationRollup(
        full_command_matrix_results=str(payload["full_command_matrix_results"]),
        matrix_runner_summary_result=str(payload["matrix_runner_summary_result"]),
        matrix_runner_output_result_path=str(payload["matrix_runner_output_result_path"]),
        targeted_mypy_result=str(payload["targeted_mypy_result"]),
        baseline_result=str(payload["baseline_result"]),
        docs_build_result=str(payload["docs_build_result"]),
        prompt_boundary_result=str(payload["prompt_boundary_result"]),
        strict_audit_result=str(payload["strict_audit_result"]),
        immutability_verifier_result=str(payload["immutability_verifier_result"]),
        unresolved_risks=str(payload["unresolved_risks"]),
    )


def verify_pr_metadata(*, pr_title: str, pr_body: str, intended_commit_title: str | None = None) -> CodexPRMetadataVerification:
    title_ok = bool(TITLE_RE.match(pr_title))
    intended_ok = True if intended_commit_title is None else (pr_title == intended_commit_title)

    normalized_body = _norm(pr_body)
    missing = tuple(marker for marker in REQUIRED_BODY_MARKERS if marker not in normalized_body)
    local_only = any(marker in normalized_body for marker in FORBIDDEN_LOCAL_ONLY_MARKERS)

    status = "codex_pr_metadata_contract_ready"
    if (not title_ok) or (not intended_ok) or missing or local_only:
        status = "codex_pr_metadata_contract_incomplete"
    return CodexPRMetadataVerification(
        status=status,
        title_ok=title_ok,
        intended_commit_title_ok=intended_ok,
        missing_body_markers=missing,
        local_only_validation_claim_detected=local_only,
    )


def build_body_from_json_text(json_text: str) -> str:
    payload = json.loads(json_text)
    return build_pr_body_from_rollup(parse_rollup_json(payload))
