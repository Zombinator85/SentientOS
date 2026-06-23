from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

WORKCELL_ARCHITECTURE_ID = "codex_workcell_architecture.v1"
AUTHORITY_LEVELS = {"none", "review_only", "proof_signal", "transition_authority", "archival_surface", "future_integration"}

NON_AUTHORITY_POSTURE: dict[str, bool] = {
    "architecture_map_is_metadata_only": True,
    "architecture_map_is_descriptive_only": True,
    "architecture_map_does_not_decide_readiness": True,
    "architecture_map_does_not_authorize_commit": True,
    "architecture_map_does_not_authorize_pr_metadata": True,
    "architecture_map_does_not_run_commands": True,
    "architecture_map_does_not_schedule_work": True,
    "architecture_map_does_not_execute_runtime_actions": True,
    "architecture_map_does_not_train_or_modify_models": True,
    "architecture_map_does_not_create_new_gates": True,
}


def _component(
    component_id: str,
    component_name: str,
    role: str,
    file_paths: list[str],
    inputs: list[str],
    outputs: list[str],
    authority_level: str,
    state_transition_power: bool,
    non_authority_boundary: str,
    failure_modes_prevented: list[str],
    reviewer_summary: str,
) -> dict[str, Any]:
    if authority_level not in AUTHORITY_LEVELS:
        raise ValueError(f"unknown_authority_level:{authority_level}")
    return {
        "component_id": component_id,
        "component_name": component_name,
        "role": role,
        "file_paths": file_paths,
        "inputs": inputs,
        "outputs": outputs,
        "authority_level": authority_level,
        "state_transition_power": state_transition_power,
        "non_authority_boundary": non_authority_boundary,
        "failure_modes_prevented": failure_modes_prevented,
        "reviewer_summary": reviewer_summary,
    }


_COMPONENTS: list[dict[str, Any]] = [
    _component("user_intent_ingress", "User intent ingress", "Receives bounded human task intent and constraints.", [], ["operator prompt", "task title"], ["task scope", "declared non-goals"], "none", False, "Intent describes requested work but does not authorize landing or runtime action.", ["scope drift", "implicit authority expansion"], "Starting surface for bounded developer-workflow work."),
    _component("codex_task_workspace", "Codex task workspace", "Holds task-owned files, diagnostics, and implementation context.", [], ["bootstrap scaffold", "repository state"], ["task-caused changes", "local evidence"], "none", False, "Workspace state is evidence context, not readiness authority.", ["lost task-owned files", "untracked evidence confusion"], "Recoverable local work area for the task."),
    _component("bootstrap_scaffold", "Bootstrap scaffold", "Checks task shape and records initial readiness or blockers.", ["scripts/bootstrap_codex_task.py"], ["task name", "task goal", "declared paths"], ["bootstrap summary"], "review_only", False, "Bootstrap can block starting work, but this architecture map does not add new bootstrap gates.", ["unknown dirty tree", "unsupported task shape"], "Initial procedural scaffold for bounded work."),
    _component("focused_tests", "Focused tests", "Provides targeted proof for changed behavior.", ["scripts/run_tests.py"], ["selected pytest files"], ["focused test result"], "proof_signal", False, "Focused tests provide proof signals only and cannot authorize commit or PR metadata.", ["claiming unexecuted tests as proof", "skipped test inflation"], "Targeted executable proof lane."),
    _component("targeted_mypy", "Targeted mypy", "Checks typed surface for changed modules and CLIs.", [], ["selected Python paths"], ["targeted mypy result"], "proof_signal", False, "Type results are proof signals, not landing decisions.", ["typing regressions", "unreviewed CLI import drift"], "Targeted static typing proof lane."),
    _component("review_packet_matrix", "Review packet matrix", "Aggregates required and diagnostic proof lanes for reviewer evidence.", ["scripts/run_work_item_review_packet_matrix.py"], ["repository state", "test lanes", "audit lanes"], ["matrix JSON"], "proof_signal", False, "Matrix supplies proof signals but does not create commits or PR metadata.", ["partial proof treated as full proof", "timed-out lanes hidden"], "Whole-work-item proof classifier."),
    _component("codex_task_lifecycle_summary", "Codex task lifecycle summary", "Summarizes phase evidence across task lifecycle.", ["sentientos/codex_task_lifecycle_summary.py"], ["matrix JSON", "finalizer JSON"], ["lifecycle summary JSON"], "review_only", False, "Lifecycle summary is interpretive context and does not decide readiness.", ["phase evidence scattered", "reviewer misses blockers"], "Compact lifecycle review surface."),
    _component("codex_lifecycle_doctor", "Codex lifecycle doctor", "Interprets landing evidence and names diagnostic posture.", ["sentientos/codex_lifecycle_doctor.py"], ["lifecycle summary", "evidence index"], ["doctor report"], "review_only", False, "Doctor interpretation is non-authoritative and cannot decide readiness.", ["unsafe next action ambiguity", "hidden missing evidence"], "Diagnostic interpreter for reviewers."),
    _component("codex_landing_evidence_index", "Codex landing evidence index", "Catalogs landing artifacts and artifact hints.", ["sentientos/codex_landing_evidence_index.py"], ["artifact paths"], ["evidence index JSON"], "review_only", False, "Evidence index catalogs artifacts but does not verify landing authority.", ["lost artifact inventory", "unlabeled missing artifacts"], "Artifact catalog for review."),
    _component("codex_landing_evidence_appendix", "Codex landing evidence appendix", "Renders reviewer-readable landing evidence context.", ["sentientos/codex_landing_evidence_appendix.py"], ["evidence index", "doctor report", "doctrine map"], ["evidence appendix markdown"], "review_only", False, "Appendix renders context but does not authorize state transition.", ["reviewer reconstructs context manually", "summary mistaken for authority"], "Human-readable evidence surface."),
    _component("codex_beneficial_trait_doctrine", "Codex beneficial trait doctrine", "Explains beneficial-trait posture of landing rails.", ["sentientos/codex_beneficial_trait_doctrine.py"], ["existing rail catalog"], ["doctrine map"], "review_only", False, "Doctrine explains traits but does not train models or decide readiness.", ["doctrine overclaim", "model-training confusion"], "Static doctrine map for review."),
    _component("appendix_provenance_sidecar", "Appendix provenance sidecar", "Identifies bytes and digests behind appendix inputs.", [], ["appendix input bytes"], ["provenance digests"], "review_only", False, "Provenance identifies bytes but does not verify authority.", ["opaque appendix inputs", "digest omission"], "Byte provenance surface."),
    _component("codex_finalize_landing", "Codex finalize landing", "Evaluates commit/pr-metadata phase readiness under landing doctrine.", ["scripts/codex_finalize_landing.py"], ["matrix JSON", "focused tests", "targeted mypy", "changed files"], ["finalizer JSON"], "transition_authority", True, "Only this finalizer is commit-readiness authority; this architecture merely describes it.", ["commit before readiness", "stale evidence landing"], "Commit readiness authority for finalizer phases."),
    _component("codex_pr_metadata_guard", "Codex PR metadata guard", "Authorizes PR metadata only after finalizer and matrix checks.", ["scripts/codex_pr_metadata_guard.py"], ["pre-commit finalizer", "pr-metadata finalizer", "matrix JSON"], ["guard summary"], "transition_authority", True, "Only this guard is PR metadata authorization authority; this architecture merely describes it.", ["PR metadata before readiness", "title contract drift"], "PR metadata boundary authority."),
    _component("git_commit_boundary", "Git commit boundary", "Represents irreversible local commit transition after readiness.", [], ["ready_to_commit finalizer"], ["git commit"], "none", False, "The boundary is acted on by git/operator procedure, not by this map.", ["unreviewed commit transition"], "Commit transition boundary."),
    _component("pr_metadata_boundary", "PR metadata boundary", "Represents PR metadata creation after guard readiness.", [], ["pr_metadata_guard_ready"], ["PR metadata"], "none", False, "The boundary does not authorize itself and this map cannot create PR metadata.", ["unguarded PR metadata"], "PR metadata transition boundary."),
    _component("sentientos_ledger", "SentientOS ledger", "Future tamper-evident landing history and receipt chain surface.", [], ["landed receipts"], ["ledger records"], "future_integration", False, "Future integration surface unless separately implemented; not current authority.", ["receipt loss", "history opacity"], "Future ledger alignment."),
    _component("glow_archive", "Glow archive", "Future/review archival memory for evidence and landed receipts.", [], ["evidence appendix", "receipts"], ["glow memory"], "archival_surface", False, "Archival surface does not decide readiness or execute work.", ["review surface loss", "evidence memory drift"], "Evidence memory alignment."),
    _component("pulse_monitor", "Pulse monitor", "Future stale-evidence, drift, timeout, and pressure signal surface.", [], ["stale evidence hints", "timeouts"], ["pulse signals"], "future_integration", False, "Pulse signals may recommend review but do not authorize action.", ["stale evidence unnoticed", "timeout pressure hidden"], "Freshness and pressure alignment."),
    _component("daemon_repair_substrate", "Daemon repair substrate", "Future bounded repair-planning and next-task recommendation surface.", [], ["pulse signals", "doctor diagnostics"], ["repair recommendations"], "future_integration", False, "Daemon substrate may recommend future tasks but must not act or schedule here.", ["unbounded self-healing", "autonomous action confusion"], "Future repair planning surface."),
    _component("vow_digest", "Vow digest", "Future canonical constraint and doctrine invariant digest surface.", [], ["AGENTS.md", "development doctrine"], ["vow digest"], "future_integration", False, "Vow digest can describe constraints but does not replace finalizer or guard.", ["constraint drift", "doctrine mismatch"], "Canonical constraint alignment."),
    _component("federation_consensus_boundary", "Federation consensus boundary", "Future drift consensus surface across federated review contexts.", [], ["federated drift reports"], ["consensus signals"], "future_integration", False, "Federation consensus is not reached or acted on by this map.", ["single-node drift overclaim", "unreviewed federation adoption"], "Future federation drift boundary."),
]


def _flow(flow_id: str, source: str, target: str, artifact: str, forbidden: str, authority: str, summary: str) -> dict[str, str]:
    return {"flow_id": flow_id, "source_component": source, "target_component": target, "artifact_or_signal": artifact, "allowed_direction": f"{source} -> {target}", "forbidden_reverse_inference": forbidden, "authority_boundary": authority, "reviewer_summary": summary}


_FLOWS: list[dict[str, str]] = [
    _flow("intent_to_bootstrap", "user_intent_ingress", "bootstrap_scaffold", "task constraints", "Bootstrap output must not invent broader user intent.", "No landing authority.", "Intent enters procedural scaffold."),
    _flow("bootstrap_to_task_workspace", "bootstrap_scaffold", "codex_task_workspace", "bootstrap summary", "Workspace edits cannot retroactively make blocked bootstrap ready.", "Blocked bootstrap stops work.", "Ready scaffold opens bounded workspace."),
    _flow("task_workspace_to_focused_proof", "codex_task_workspace", "focused_tests", "changed files and selected tests", "Passing focused tests cannot prove untested workspace behavior.", "Proof signal only.", "Task changes receive focused proof."),
    _flow("focused_proof_to_matrix", "focused_tests", "review_packet_matrix", "focused test result", "Matrix cannot convert skipped focused tests into executed proof.", "Proof signal only.", "Focused proof feeds matrix classification."),
    _flow("matrix_to_finalizer", "review_packet_matrix", "codex_finalize_landing", "matrix JSON", "Finalizer readiness cannot be inferred from matrix alone.", "Finalizer remains commit-readiness authority.", "Matrix evidence is consumed by finalizer."),
    _flow("matrix_to_lifecycle_summary", "review_packet_matrix", "codex_task_lifecycle_summary", "matrix status", "Lifecycle summary cannot upgrade matrix failures.", "Review only.", "Matrix posture is summarized."),
    _flow("lifecycle_summary_to_doctor", "codex_task_lifecycle_summary", "codex_lifecycle_doctor", "lifecycle summary", "Doctor advice cannot rewrite source evidence.", "Review only.", "Doctor interprets lifecycle evidence."),
    _flow("artifacts_to_evidence_index", "codex_task_workspace", "codex_landing_evidence_index", "artifact paths", "Index presence cannot imply artifact freshness or readiness.", "Review only.", "Artifacts are cataloged."),
    _flow("index_doctor_doctrine_to_appendix", "codex_landing_evidence_index", "codex_landing_evidence_appendix", "index, doctor, doctrine context", "Appendix rendering cannot authorize state transition.", "Review only.", "Evidence context is rendered for reviewers."),
    _flow("appendix_to_reviewer_surface", "codex_landing_evidence_appendix", "glow_archive", "review appendix", "Archive presence cannot imply readiness.", "Archival/review only.", "Appendix can be archived as review surface."),
    _flow("finalizer_to_commit_boundary", "codex_finalize_landing", "git_commit_boundary", "ready_to_commit", "A commit cannot prove finalizer readiness after the fact.", "Finalizer is only commit-readiness authority.", "Commit boundary follows finalizer readiness."),
    _flow("pr_metadata_finalizer_to_guard", "codex_finalize_landing", "codex_pr_metadata_guard", "ready_for_pr_metadata", "Guard readiness cannot be inferred without pr-metadata finalizer evidence.", "Guard remains PR metadata authority.", "Finalizer evidence feeds guard."),
    _flow("guard_to_pr_metadata_boundary", "codex_pr_metadata_guard", "pr_metadata_boundary", "pr_metadata_guard_ready", "PR metadata cannot retroactively authorize itself.", "Guard is only PR metadata authorization authority.", "PR metadata boundary follows guard readiness."),
    _flow("landed_receipts_to_ledger", "pr_metadata_boundary", "sentientos_ledger", "landed receipts", "Ledger entries cannot authorize the prior landing.", "Future archival surface.", "Receipts may be ledgered in future integration."),
    _flow("evidence_to_glow_archive", "codex_landing_evidence_appendix", "glow_archive", "evidence review surface", "Glow memory cannot decide readiness.", "Archival surface.", "Evidence can align with glow memory."),
    _flow("stale_or_pressure_signal_to_pulse", "codex_lifecycle_doctor", "pulse_monitor", "stale or pressure signal", "Pulse cannot make stale evidence fresh.", "Future signal surface.", "Diagnostics may inform pulse."),
    _flow("pulse_to_daemon_repair_recommendation", "pulse_monitor", "daemon_repair_substrate", "repair pressure signal", "Daemon recommendation cannot execute itself.", "Future recommendation only.", "Pulse may inform bounded repair planning."),
    _flow("daemon_to_future_codex_task", "daemon_repair_substrate", "user_intent_ingress", "future task recommendation", "Recommendation cannot become user consent or scheduling authority.", "Future/review only.", "Repair recommendations return through human intent ingress."),
    _flow("federation_consensus_to_drift_control", "federation_consensus_boundary", "vow_digest", "drift consensus signal", "Consensus signal cannot override canonical local authority.", "Future integration only.", "Federation signals may inform drift review."),
]

AUTHORITY_BOUNDARIES: list[str] = [
    "codex_finalize_landing is the only commit-readiness authority.",
    "codex_pr_metadata_guard is the only PR metadata authorization authority.",
    "review_packet_matrix supplies proof signals but does not create PR metadata.",
    "codex_lifecycle_doctor interprets evidence but does not decide readiness.",
    "codex_landing_evidence_index catalogs artifacts but does not verify landing authority.",
    "codex_landing_evidence_appendix renders review context but does not authorize state transition.",
    "codex_beneficial_trait_doctrine explains traits but does not train models or decide readiness.",
    "appendix_provenance_sidecar identifies bytes but does not verify authority.",
    "ledger/glow/pulse/daemon/federation integration points are future surfaces unless separately implemented.",
]

SENTIENTOS_MOUNT_ALIGNMENT: dict[str, dict[str, Any]] = {
    "/daemon": {"purpose": "repair planning, bounded next-task generation, self-healing substrate", "components": ["daemon_repair_substrate"]},
    "/glow": {"purpose": "archived evidence, landed receipts, review surfaces", "components": ["glow_archive", "codex_landing_evidence_appendix"]},
    "/ledger": {"purpose": "tamper-evident landing history and receipt chain", "components": ["sentientos_ledger"]},
    "/pulse": {"purpose": "freshness, drift, timeout, pressure, and rerun signals", "components": ["pulse_monitor", "codex_lifecycle_doctor"]},
    "/vow": {"purpose": "canonical constraints, vow digest, doctrine invariants", "components": ["vow_digest", "codex_beneficial_trait_doctrine"]},
}

FUTURE_INTEGRATION_POINTS: list[dict[str, str]] = [
    {"integration_id": "canonical_vow_digest_checks", "status": "future_integration", "authority_posture": "review_only", "description": "Compare current doctrine constraints against canonical vow digests without replacing finalizer or guard authority."},
    {"integration_id": "daemon_repair_recommendation", "status": "future_integration", "authority_posture": "review_only", "description": "Recommend bounded follow-up repair tasks without scheduling or executing them."},
    {"integration_id": "federation_drift_consensus", "status": "future_integration", "authority_posture": "review_only", "description": "Surface federated drift signals for review without adopting external authority."},
    {"integration_id": "glow_evidence_memory", "status": "future_integration", "authority_posture": "archival_surface", "description": "Archive evidence and review surfaces as memory without deciding readiness."},
    {"integration_id": "ledger_receipt_archival", "status": "future_integration", "authority_posture": "archival_surface", "description": "Record landed receipts after authorized transitions without authorizing them."},
    {"integration_id": "operator_cockpit_rendering", "status": "future_integration", "authority_posture": "review_only", "description": "Render workcell health and evidence to operators without introducing new gates."},
    {"integration_id": "pulse_stale_evidence_watch", "status": "future_integration", "authority_posture": "review_only", "description": "Watch for stale evidence and timeout pressure as signals, not readiness decisions."},
    {"integration_id": "workcell_health_snapshot", "status": "future_integration", "authority_posture": "review_only", "description": "Summarize workcell health for reviewers without runtime execution or scheduling."},
]


def build_codex_workcell_architecture() -> dict[str, Any]:
    components = sorted((dict(component) for component in _COMPONENTS), key=lambda item: item["component_id"])
    flows = sorted((dict(flow) for flow in _FLOWS), key=lambda item: item["flow_id"])
    known = {component["component_id"] for component in components}
    for flow in flows:
        if flow["source_component"] not in known or flow["target_component"] not in known:
            raise ValueError(f"unknown_flow_component:{flow['flow_id']}")
    return {
        "workcell_architecture_id": WORKCELL_ARCHITECTURE_ID,
        "metadata_only": True,
        "architecture_only": True,
        "developer_workflow_evidence_only": True,
        "not_runtime_authority": True,
        "not_scheduler": True,
        "not_executor": True,
        "not_model_training": True,
        "not_reinforcement_learning": True,
        "components": components,
        "flows": flows,
        "authority_boundaries": list(AUTHORITY_BOUNDARIES),
        "sentientos_mount_alignment": dict(sorted(SENTIENTOS_MOUNT_ALIGNMENT.items())),
        "future_integration_points": sorted((dict(item) for item in FUTURE_INTEGRATION_POINTS), key=lambda item: item["integration_id"]),
        "non_authority_posture": dict(sorted(NON_AUTHORITY_POSTURE.items())),
    }


def render_codex_workcell_architecture_markdown(architecture: Mapping[str, Any] | None = None) -> str:
    payload = architecture or build_codex_workcell_architecture()
    lines = [
        "# Codex Workcell Architecture",
        "",
        "Codex is described here as a bounded SentientOS developer-workflow workcell: ingress, workspace, proof, interpretation, review, authority, memory, pulse, daemon, and federation surfaces remain separated. This map is metadata-only architecture doctrine, not runtime authority.",
        "",
        "## Components",
        "| component_id | authority_level | state_transition_power | reviewer_summary |",
        "| --- | --- | --- | --- |",
    ]
    for component in payload["components"]:
        lines.append(f"| {component['component_id']} | {component['authority_level']} | {'true' if component['state_transition_power'] else 'false'} | {component['reviewer_summary']} |")
    lines.extend(["", "## Flows", "| flow_id | source | target | authority_boundary |", "| --- | --- | --- | --- |"])
    for flow in payload["flows"]:
        lines.append(f"| {flow['flow_id']} | {flow['source_component']} | {flow['target_component']} | {flow['authority_boundary']} |")
    lines.extend(["", "## Authority boundaries"])
    for boundary in payload["authority_boundaries"]:
        lines.append(f"- {boundary}")
    lines.extend(["", "## SentientOS mount alignment"])
    for mount, details in payload["sentientos_mount_alignment"].items():
        lines.append(f"- **{mount}:** {details['purpose']} ({', '.join(details['components'])})")
    lines.extend(["", "## Future integration"])
    for item in payload["future_integration_points"]:
        lines.append(f"- **{item['integration_id']}** ({item['status']}, {item['authority_posture']}): {item['description']}")
    lines.extend(["", "## Non-authority posture"])
    for key, value in payload["non_authority_posture"].items():
        lines.append(f"- **{key}:** {'true' if value else 'false'}")
    lines.append("")
    return "\n".join(lines)


def write_codex_workcell_architecture_json(architecture: Mapping[str, Any], output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(architecture, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_codex_workcell_architecture_markdown(markdown: str, output: str) -> None:
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(markdown, encoding="utf-8")
