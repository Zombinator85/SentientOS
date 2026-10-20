from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.goal_executor import ExecutorState, GoalExecutor
from sentientos.integrity_quarantine import load_state as load_quarantine_state
from sentientos.integrity_controller import evaluate_integrity
from sentientos.integrity_pressure import compute_integrity_pressure
from sentientos.policy_fingerprint import emit_policy_fingerprint
from sentientos.risk_budget import compute_risk_budget
from sentientos.strategic_posture import resolve_posture
from sentientos.throughput_policy import derive_throughput_policy
from sentientos.work_plan import (
    WORK_PLAN_DIR,
    WorkPlanError,
    load_work_plan,
    load_work_plan_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute work plan file")
    parser.add_argument("plan_path")
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    plan_path = Path(args.plan_path).resolve()
    plan = load_work_plan(plan_path)
    expected_evidence_digest: str | None = None
    goal_graph_hash = "manual"
    allocation_id = "manual"
    allocation_artifact_digest: str | None = None
    if plan_path.parent == root / WORK_PLAN_DIR:
        # Persisted canonical plans carry a separately validated rationale.
        # Verify it before reading execution policy or opening executor state.
        evidence = load_work_plan_evidence(root, plan)
        digest = evidence.get("evidence_digest")
        binding = evidence.get("evidence_binding")
        binding_goal_graph_hash = (
            binding.get("goal_graph_hash") if isinstance(binding, dict) else None)
        binding_allocation_id = (
            binding.get("allocation_artifact_path") if isinstance(binding, dict) else None)
        binding_allocation_digest = (
            binding.get("allocation_artifact_digest") if isinstance(binding, dict) else None)
        if (not isinstance(digest, str) or not isinstance(binding, dict)
                or not isinstance(binding_goal_graph_hash, str)
                or not isinstance(binding_allocation_id, str)
                or (binding_allocation_digest is not None
                    and not isinstance(binding_allocation_digest, str))):
            raise WorkPlanError("canonical_work_plan_evidence_identity_missing")
        expected_evidence_digest = digest
        goal_graph_hash = binding_goal_graph_hash
        allocation_id = binding_allocation_id
        allocation_artifact_digest = binding_allocation_digest
    quarantine = load_quarantine_state(root)
    pressure = compute_integrity_pressure(root)
    throughput = derive_throughput_policy(
        integrity_pressure_level=pressure.level, quarantine=quarantine)
    posture = resolve_posture()
    budget = compute_risk_budget(
        repo_root=root, posture=posture.posture, pressure_level=pressure.level,
        operating_mode=throughput.mode, quarantine_active=quarantine.active)
    policy_fingerprint = emit_policy_fingerprint(root)
    integrity = evaluate_integrity(root, policy_hash=policy_fingerprint.policy_hash)
    state = ExecutorState(
        repo_root=root,
        created_at=plan.created_at,
        context=plan.context,
        operating_mode=throughput.mode,
        quarantine_active=quarantine.active,
        allow_mutation=(not quarantine.active
            and throughput.allow_forge_mutation
            and integrity.mutation_allowed
            and budget.forge_max_files_changed > 0),
        goal_graph_hash=goal_graph_hash,
        allocation_id=allocation_id,
        allocation_artifact_digest=allocation_artifact_digest,
        risk_budget=budget,
        pressure_level=pressure.level,
        posture=posture.posture,
    )
    run = GoalExecutor(repo_root=root).execute_plan(
        plan, state, expected_evidence_digest=expected_evidence_digest)
    print(json.dumps(run.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
