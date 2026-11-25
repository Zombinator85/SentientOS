from pathlib import Path
import json
import os
import runpy

repo = Path("/mnt/c/Users/aprmu/Documents/Codex/cc-cognition-next")
out = repo / "artifacts/experiments/identity-neutral-journal-recovery-20261125-terminal-binding-v1"
workspace = Path(
    "/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl")
experiment = workspace / "sentientos-data/rootless-experimental"
manifest = experiment / "ollama-model-manifests/ebb2efeea46036ca7f276589e710729aff06c3a4b7b7b970c09da1712daf0989.json"
plan_path = out / "execution_independent_v2.json"
plan = json.loads(plan_path.read_text())
script = repo / "scripts/run_rootless_ollama_embodied_cognition_cycle.py"
for seed in (13688613, 13688614):
    trial = next(row for row in plan["trials"]
        if row["task_generation_seed"] == seed)
    run_id = trial["runner_cycle_id"]
    run_root = experiment / "developmental-cognition-cycles" / run_id
    if run_root.exists() or run_root.is_symlink():
        raise SystemExit(f"reserved_run_root_already_exists:{run_id}")
    env = {
        "SENTIENTOS_ROOTLESS_EXPERIMENT_WORKSPACE": str(workspace),
        "SENTIENTOS_SOURCE_PROVENANCE_GIT": "/mnt/c/Program Files/Git/cmd/git.exe",
        "SENTIENTOS_HERMES_MODEL": "hf.co/bartowski/NousResearch_Hermes-4-14B-GGUF:Q4_K_M",
        "SENTIENTOS_HERMES_MODEL_MANIFEST_PATH": str(manifest),
        "SENTIENTOS_HERMES_GPU_LAYERS": "32",
        "SENTIENTOS_HERMES_CYCLE_ID": run_id,
        "SENTIENTOS_HERMES_EXPERIMENT_SEED": str(seed),
        "SENTIENTOS_HERMES_BACKEND_SEED": "42",
        "SENTIENTOS_HERMES_PREREGISTRATION_DIGEST": plan["execution_plan_digest"].removeprefix("sha256:"),
        "SENTIENTOS_ROOTLESS_PRIOR_HISTORY_ROOT": str(experiment / "developmental-cognition-cycles/rootless-cognition-cycle-20261124000000000009/resident-cognition/history"),
        "SENTIENTOS_HERMES_HISTORICAL_PAIR_PLAN_PATH": str(plan_path),
        "SENTIENTOS_HERMES_HISTORICAL_PAIR_COHORT_PATH": str(out / "cohort_bound.json"),
        "SENTIENTOS_HERMES_HISTORICAL_PAIR_ANALYSIS_PATH": str(out / "analysis_independent_v2.json"),
        "SENTIENTOS_HERMES_HISTORICAL_PAIR_JOURNAL_ROOT": str(experiment / "cognition-preflight-private/20261125-terminal-binding-v1"),
        "SENTIENTOS_HERMES_HISTORICAL_PAIR_PARITY_AUDIT_PATH": str(out / f"parity_{seed}.json"),
        "SENTIENTOS_HERMES_HISTORICAL_PAIR_ALLOWLIST_PATH": str(out / f"allowlist_{seed}.json"),
        "SENTIENTOS_HERMES_HISTORICAL_PAIR_VERIFICATION_PATH": str(out / f"matched_pair_{seed}.json"),
        "SENTIENTOS_HERMES_HISTORICAL_PAIR_LEFT_PREFLIGHT_PATH": str(out / f"hermes_{seed}_preflight.json"),
        "SENTIENTOS_HERMES_HISTORICAL_PAIR_RIGHT_PREFLIGHT_PATH": str(out / f"qwen_{seed}_preflight.json"),
        "SENTIENTOS_HERMES_HISTORICAL_PAIR_LEFT_PREFLIGHT_VERIFICATION_PATH": str(out / f"hermes_{seed}_preflight.json.verified.json"),
        "SENTIENTOS_HERMES_HISTORICAL_PAIR_RIGHT_PREFLIGHT_VERIFICATION_PATH": str(out / f"qwen_{seed}_preflight.json.verified.json"),
    }
    os.environ.update(env)
    namespace = runpy.run_path(str(script),
        run_name="sentientos_cpu_identity_preflight")
    context = namespace["_load_historical_pair_execution_context"]()
    manifest_path = namespace["_resolve_pinned_model_manifest_path"]()
    manifest_digest, manifest_size = namespace["stream_sha256"](manifest_path)
    evidence = namespace["_preflight_historical_pair_model_identity"](
        context=context, manifest_path=manifest_path,
        manifest_digest=manifest_digest, manifest_size=manifest_size)
    if (evidence.get("status") != "matched_without_model_load"
            or evidence.get("run_root_allocated") is not False
            or evidence.get("model_loaded") is not False
            or evidence.get("model_invoked") is not False):
        raise SystemExit(f"identity_preflight_posture_invalid:{run_id}")
    evidence_path = namespace[
        "_preflight_historical_pair_model_identity"].__globals__[
            "HISTORICAL_PAIR_MODEL_IDENTITY_PREFLIGHT_PATH"]
    print(json.dumps({"run_id": run_id, "seed": seed,
        "status": evidence["status"],
        "predicted_identity_digest": evidence[
            "predicted_model_identity_digest"],
        "target_identity_digest": evidence[
            "target_model_identity_digest"],
        "run_root_allocated": False, "model_loaded": False,
        "model_invoked": False, "evidence_path": evidence_path},
        sort_keys=True))
    for key in env:
        os.environ.pop(key, None)
