"""Build the production embodied-decision request without invoking a model.

The helper uses the actual companion bridge and cognition owner, then stops at
the governed invocation boundary. Its report contains prompt digests, sizes,
and evidence IDs only; no prompt, model output, or action is persisted.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class _PreviewCaptured(Exception):
    pass


class _PreviewInvoker:
    """Supply a valid request shape and stop before any backend entry."""

    def __init__(self) -> None:
        self.requests: list[Any] = []

    def build_request(self, **kwargs: Any) -> Any:
        from sentientos.governed_local_model_invocation import (
            LocalModelInvocationRequest,
        )

        request = LocalModelInvocationRequest(
            purpose=kwargs["purpose"], prompt=kwargs["prompt"],
            model_id="rootless-prompt-preview-only",
            authority_map_digest="0" * 64, model_artifact_digest=None,
            caller=kwargs["caller"], lifecycle_phase=kwargs.get(
                "lifecycle_phase", "runtime"),
            correlation_id=kwargs["correlation_id"],
            expected_output_format=kwargs.get("expected_output_format", "text"),
            budget=kwargs["budget"],
            upstream_evidence=kwargs.get("upstream_evidence", {}),
            linkage=kwargs.get("linkage", {}),
            structured_output_schema=kwargs.get("structured_output_schema"),
        )
        self.requests.append(request)
        return request

    def invoke(self, request: Any, **_: Any) -> Any:
        if not self.requests or self.requests[-1] is not request:
            raise RuntimeError("prompt_preview_request_binding_invalid")
        raise _PreviewCaptured


def _load_runner_module(module_path: Path) -> Any:
    name = "_rootless_embodied_runner_prompt_preflight"
    spec = importlib.util.spec_from_file_location(name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("rootless_embodied_runner_import_failed")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _preview_one(bridge: Any, invoker: _PreviewInvoker, *, request_id: str,
        question: str, withhold_history: bool) -> dict[str, Any]:
    try:
        bridge.respond(request_id=request_id, question=question,
            withhold_developmental_history=withhold_history)
    except _PreviewCaptured:
        pass
    else:
        raise RuntimeError("prompt_preview_did_not_stop_at_invocation_boundary")
    if not invoker.requests:
        raise RuntimeError("prompt_preview_request_missing")
    request = invoker.requests[-1]
    prompt = request.prompt
    prompt_bytes = prompt.encode("utf-8")
    upstream = dict(request.upstream_evidence)
    return {
        "prompt_sha256": hashlib.sha256(prompt_bytes).hexdigest(),
        "prompt_chars": len(prompt),
        "prompt_bytes": len(prompt_bytes),
        "max_input_chars": request.budget.max_input_chars,
        "within_owner_limit": len(prompt) <= request.budget.max_input_chars,
        "current_fact_ids": list(upstream.get("current_fact_ids", ())),
        "snapshot_digest": upstream.get("snapshot_digest"),
        "current_projection_digest": upstream.get("current_projection_digest"),
        "history_record_ids": list(upstream.get("record_ids", ())),
        "history_withheld": withhold_history,
    }


def build_preflight_report(*, plan_path: Path, cycle_index: int) -> dict[str, Any]:
    from work.rootless_history_boundary_campaign import (
        _load_plan, _plan_model_identity_digests,
    )

    plan = _load_plan(plan_path)
    cycle_ids = plan.get("ordered_cycle_ids")
    task_seeds = plan.get("ordered_task_generation_seeds")
    identity_digests = _plan_model_identity_digests(plan)
    if (not isinstance(cycle_ids, list) or not isinstance(task_seeds, list)
            or not isinstance(identity_digests, list)
            or type(cycle_index) is not int
            or not 0 <= cycle_index < len(cycle_ids)
            or len(task_seeds) != len(cycle_ids)
            or len(identity_digests) != len(cycle_ids)):
        raise ValueError("prompt_preflight_campaign_cycle_binding_invalid")

    # Importing the experiment runner initializes only its private custody
    # paths. The fake invoker below prevents all model/backend entry.
    with tempfile.TemporaryDirectory(prefix="sentientos-decision-prompt-") as temp:
        temp_root = Path(temp)
        workspace = temp_root / "experiment-workspace"
        os.environ["SENTIENTOS_ROOTLESS_EXPERIMENT_WORKSPACE"] = str(workspace)
        runner = _load_runner_module(
            REPO_ROOT / "scripts" / "run_rootless_ollama_embodied_cognition_cycle.py")

        from sentientos.developmental_companion_bridge import (
            ResidentDevelopmentalCompanionBridge,
        )
        from sentientos.runtime_admission import (
            AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier,
        )

        history_root = temp_root / "history"
        state_root = temp_root / "state"
        history_root.mkdir(mode=0o700)
        state_root.mkdir(mode=0o700)
        ledger = AdmissionLedger(state_root / "runtime_admissions.json")
        definitions = {runner.RESIDENT_DEVELOPMENTAL_WRITEBACK:
            runner.RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION}

        def current_sequence() -> int:
            admissions, _ = ledger.load()
            return max((row.issued_sequence for row in admissions), default=0)

        def next_sequence() -> int:
            admissions, revocations = ledger.load()
            return max([row.issued_sequence for row in admissions]
                + [row.sequence for row in revocations], default=0) + 1

        invoker = _PreviewInvoker()
        writeback = runner.ResidentDevelopmentalWritebackController(
            history_root=history_root,
            admission_verifier=RuntimeAdmissionVerifier(
                definitions=definitions, ledger=ledger),
            current_sequence=current_sequence)
        owner = runner.ResidentDevelopmentalCognitionOwner(
            config=runner.ResidentDevelopmentalCognitionConfig(
                history_root, state_root, ("embodiment",), 16, 4, False,
                max_inference_input_chars=(
                    runner.ROOTLESS_DEVELOPMENTAL_COGNITION_INPUT_CHAR_LIMIT),
                max_inference_timeout_seconds=(
                    runner.ROOTLESS_DEVELOPMENTAL_COGNITION_INFERENCE_TIMEOUT_SECONDS)),
            writeback=writeback,
            admission_authority=RuntimeAdmissionAuthority(
                definitions=definitions, ledger=ledger),
            invoker=invoker, current_sequence=next_sequence)

        scenario = runner._synthetic_pre_action_scenario_observation()
        target = runner._synthetic_current_target_observation()
        captured_at = datetime.now(timezone.utc)
        bridge = ResidentDevelopmentalCompanionBridge(owner,
            proprioception_provider=lambda: (scenario, target),
            clock=lambda: captured_at)
        base = _preview_one(bridge, invoker,
            request_id="rootless-cognition-cycle-00000000000000000001:pre-action-decision",
            question=runner.PRE_ACTION_DECISION_QUESTION,
            withhold_history=True)

        # Search the largest 4-byte Unicode ask that passes both independent
        # bounds: 1,024 source bytes and the cognition owner's question limit.
        largest_supported_ask = ""
        clarification_question = runner._pre_action_clarification_question("")
        for codepoint_count in range(256, -1, -1):
            candidate_ask = "\U0010ffff" * codepoint_count
            candidate_question = runner._pre_action_clarification_question(
                candidate_ask)
            if (len(candidate_ask.encode("utf-8")) <= 1024
                    and len(candidate_question)
                        <= runner.MAX_COGNITION_REQUEST_QUESTION_CHARS):
                largest_supported_ask = candidate_ask
                clarification_question = candidate_question
                break
        else:
            raise RuntimeError("clarification_question_has_no_valid_ask_bound")
        refresh_at = datetime.now(timezone.utc)
        refresh_target = runner._synthetic_current_target_refresh_observation(
            observed_at=refresh_at.isoformat())
        refresh_bridge = ResidentDevelopmentalCompanionBridge(owner,
            proprioception_provider=lambda: (scenario, refresh_target),
            clock=lambda: refresh_at)
        clarification = _preview_one(refresh_bridge, invoker,
            request_id="rootless-cognition-cycle-00000000000000000001:pre-action-clarification",
            question=clarification_question, withhold_history=True)

        source = runner.RUN_SOURCE_PROVENANCE
        source_digest = source.get("worktree_content_digest")
        if (source.get("observation_status") != "observed"
                or source.get("worktree_content_status") != "complete"
                or not isinstance(source_digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", source_digest) is None):
            raise RuntimeError("prompt_preflight_source_provenance_incomplete")
        source_after = runner._source_provenance()
        source_stable = (
            source_after.get("observation_status") == "observed"
            and source_after.get("worktree_content_status") == "complete"
            and source_after.get("worktree_content_digest") == source_digest
            and source_after.get("worktree_status_digest") ==
                source.get("worktree_status_digest"))
        if not source_stable:
            raise RuntimeError("prompt_preflight_source_changed_during_preview")
        body: dict[str, Any] = {
            "schema_version": "sentientos.rootless_embodied_decision_prompt_preflight:v1",
            "campaign_binding": {
                "campaign_id": plan["campaign_id"],
                "campaign_plan_digest": plan["plan_digest"],
                "cycle_index": cycle_index,
                "cycle_id": cycle_ids[cycle_index],
                "task_generation_seed": task_seeds[cycle_index],
                "target_model_identity_digest": identity_digests[cycle_index],
            },
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "source_worktree_content_digest": source_digest,
            "source_provenance_stable_during_preview": source_stable,
            "initial_decision": base,
            "maximum_bounded_clarification": clarification,
            "clarification_sensor_refresh": {
                "source_id": refresh_target.source_id,
                "source_schema": refresh_target.source_schema,
                "source_digest": refresh_target.source_digest,
                "observed_at": refresh_target.observed_at,
                "provenance_class": refresh_target.provenance_class,
                "evidence_class": refresh_target.evidence_class,
                "synthetic": True,
                "physical_world_observation": False,
            },
            "clarification_ask_bound": {
                "source_bytes": len(largest_supported_ask.encode("utf-8")),
                "question_chars": len(clarification_question),
                "question_char_limit": (
                    runner.MAX_COGNITION_REQUEST_QUESTION_CHARS),
                "worst_case_json_escaped_unicode": True,
            },
            "inference_performed": False,
            "backend_entry_performed": False,
            "learning_established": False,
            "authority": False,
            "raw_prompt_persisted": False,
            "model_output_persisted": False,
            "synthetic_action_simulated": False,
        }
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False).encode("utf-8")
        body["report_digest"] = hashlib.sha256(canonical).hexdigest()
        return body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--cycle-index", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_preflight_report(plan_path=args.plan,
        cycle_index=args.cycle_index)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "campaign_id": report["campaign_binding"]["campaign_id"],
        "plan_digest": report["campaign_binding"]["campaign_plan_digest"],
        "cycle_id": report["campaign_binding"]["cycle_id"],
        "initial_prompt_chars": report["initial_decision"]["prompt_chars"],
        "initial_within_limit": report["initial_decision"]["within_owner_limit"],
        "clarification_prompt_chars": report[
            "maximum_bounded_clarification"]["prompt_chars"],
        "clarification_within_limit": report[
            "maximum_bounded_clarification"]["within_owner_limit"],
        "inference_performed": report["inference_performed"],
        "backend_entry_performed": report["backend_entry_performed"],
        "report_digest": report["report_digest"],
    }, sort_keys=True))
    return 0 if (report["initial_decision"]["within_owner_limit"]
        and report["maximum_bounded_clarification"]["within_owner_limit"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
