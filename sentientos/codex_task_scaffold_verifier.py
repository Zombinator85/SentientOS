from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

REQUIRED_CLAUSES = (
    "Whole-System Codex Operating Doctrine",
    "Critical landing rule",
    "Do not return 'feature exists but full matrix not run.'",
    "Do not create PR metadata before green final validation.",
)
REQUIRED_VALIDATION_COMMANDS = (
    "python -m scripts.run_tests",
    "python -m mypy",
)
REQUIRED_REPORT_CONTRACT = (
    "exact files changed",
    "full command matrix results",
    "unresolved risks",
)
REQUIRED_TITLE_PREFIX = "[codex:"


@dataclass(frozen=True)
class CodexTaskScaffoldVerification:
    status: str
    missing_doctrine_clauses: tuple[str, ...]
    missing_validation_commands: tuple[str, ...]
    missing_report_contract_items: tuple[str, ...]
    title_discipline_ok: bool
    forbidden_surface_coverage_ok: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def verify_codex_task_scaffold_payload(payload: dict[str, Any]) -> CodexTaskScaffoldVerification:
    scaffold_value = payload.get("scaffold")
    scaffold: dict[str, Any] = scaffold_value if isinstance(scaffold_value, dict) else {}
    generated_prompt = str(scaffold.get("generated_prompt", ""))
    validation_commands = tuple(str(x) for x in scaffold.get("validation_commands", ()))
    report_contract = tuple(str(x) for x in scaffold.get("final_report_contract", ()))
    forbidden_surfaces = tuple(str(x).lower() for x in scaffold.get("forbidden_surfaces", ()))
    commit_title = str(scaffold.get("commit_pr_title", ""))

    missing_doctrine = tuple(clause for clause in REQUIRED_CLAUSES if clause not in generated_prompt)
    missing_commands = tuple(cmd for cmd in REQUIRED_VALIDATION_COMMANDS if not any(cmd in item for item in validation_commands))
    missing_report = tuple(item for item in REQUIRED_REPORT_CONTRACT if item not in report_contract)
    title_ok = commit_title.startswith(REQUIRED_TITLE_PREFIX) and "] " in commit_title
    forbidden_ok = "do not invoke codex." in forbidden_surfaces and any("provider" in s for s in forbidden_surfaces)

    status = "codex_task_scaffold_verifier_ready"
    if missing_doctrine or missing_commands or missing_report or not title_ok or not forbidden_ok:
        status = "codex_task_scaffold_verifier_incomplete"

    return CodexTaskScaffoldVerification(
        status=status,
        missing_doctrine_clauses=missing_doctrine,
        missing_validation_commands=missing_commands,
        missing_report_contract_items=missing_report,
        title_discipline_ok=title_ok,
        forbidden_surface_coverage_ok=forbidden_ok,
    )
