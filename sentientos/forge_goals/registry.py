"""Goal registry and resolver for CathedralForge."""

from __future__ import annotations

from dataclasses import dataclass
import shlex

from sentientos.forge_model import CommandSpec, ForgePhase


@dataclass(slots=True)
class GoalSpec:
    goal_id: str
    description: str
    phases: list[ForgePhase]
    apply_commands: list[CommandSpec]
    gate_profile: str
    touched_paths_globs: list[str]
    risk_notes: list[str]
    rollback_notes: list[str]


def _default_phases(goal_text: str) -> list[ForgePhase]:
    return [
        ForgePhase(
            summary="Scope and stage a coherent multi-file transformation plan.",
            touched_paths_globs=["sentientos/**/*.py", "scripts/**/*.py", "tests/**/*.py"],
            commands_to_run=[
                "python -m scripts.contract_drift",
                "python -m scripts.emit_contract_status",
                "python -m scripts.run_tests -q",
            ],
            expected_contract_impact="No unmanaged contract drift; all drift is explicit and reviewed.",
        ),
        ForgePhase(
            summary=f"Apply transformation strategy for goal '{goal_text}'.",
            touched_paths_globs=["**/*.py", "**/*.json", ".github/workflows/*.yml"],
            commands_to_run=[
                "python -m scripts.contract_drift",
                "python -m scripts.emit_contract_status",
                "python -m scripts.run_tests -q",
            ],
            expected_contract_impact="Contract status rollup captures new baseline compatibility.",
        ),
    ]


def _commands(*items: tuple[str, str]) -> list[CommandSpec]:
    return [CommandSpec(step=step, argv=shlex.split(command)) for step, command in items]


def _baseline_reclamation() -> GoalSpec:
    return GoalSpec(
        goal_id="baseline_reclamation",
        description="Stabilize the default test baseline with deterministic, low-risk repairs.",
        phases=_default_phases("baseline_reclamation"),
        apply_commands=[],
        gate_profile="default",
        touched_paths_globs=["sentientos/**/*.py", "scripts/**/*.py", "tests/**/*.py"],
        risk_notes=[
            "Automatic stabilization can hide deeper architecture debt if not accompanied by follow-up tasks.",
            "Bulk formatting changes can increase merge conflicts temporarily.",
        ],
        rollback_notes=[
            "Revert baseline_reclamation commit and replay only deterministic fixes.",
            "Use docket artifacts to replay decisions manually when needed.",
        ],
    )


def _forge_self_hosting() -> GoalSpec:
    return GoalSpec(
        goal_id="forge_self_hosting",
        description="Refactor CathedralForge internals around GoalSpec-driven execution.",
        phases=_default_phases("forge_self_hosting"),
        apply_commands=_commands(
            ("typecheck_forge", "mypy sentientos/cathedral_forge.py sentientos/forge_goals"),
            ("forge_smoke", "python -m sentientos.forge run forge_smoke_noop"),
        ),
        gate_profile="default",
        touched_paths_globs=["sentientos/cathedral_forge.py", "sentientos/forge_goals/**/*.py", "tests/test_cathedral_forge.py"],
        risk_notes=["Self-hosting changes can create recursion failure modes without strong smoke tests."],
        rollback_notes=["Restore prior forge entrypoint and rerun forge_smoke_noop before reattempting."],
    )


REGISTRY: dict[str, GoalSpec] = {
    "baseline_reclamation": _baseline_reclamation(),
    "forge_self_hosting": _forge_self_hosting(),
}


def resolve_goal(goal: str) -> GoalSpec:
    if goal in REGISTRY:
        return REGISTRY[goal]
    if goal == "forge_smoke_noop" or goal.startswith("forge_smoke_"):
        return GoalSpec(
            goal_id="forge_smoke_noop",
            description="No-op smoke run for CathedralForge.",
            phases=_default_phases(goal),
            apply_commands=[],
            gate_profile="smoke_noop",
            touched_paths_globs=["sentientos/cathedral_forge.py", "tests/test_cathedral_forge.py"],
            risk_notes=["Smoke profile only validates forge plumbing."],
            rollback_notes=["No repo changes expected."],
        )
    return GoalSpec(
        goal_id="adhoc",
        description=f"Ad-hoc goal: {goal}",
        phases=_default_phases(goal),
        apply_commands=[],
        gate_profile="default",
        touched_paths_globs=["sentientos/**/*.py", "scripts/**/*.py", "tests/**/*.py"],
        risk_notes=["Ad-hoc goals require manual review for command safety."],
        rollback_notes=["Revert ad-hoc changes and rerun contract gates."],
    )
