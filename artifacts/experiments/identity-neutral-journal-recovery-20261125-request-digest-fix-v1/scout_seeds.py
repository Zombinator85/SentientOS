from pathlib import Path
from dataclasses import replace
import json
import sys

sys.path.insert(0, "/mnt/c/Users/aprmu/Documents/Codex/cc-cognition-next")
from scripts.preflight_resident_historical_examples_pair import (
    _history_probe_overlap_audit, _read_private_task_commitment_key)
from sentientos.developmental_model_replacement_experiment import (
    ROOTLESS_INTEGER_AFFINE_WIDE_TRANSFER_TASK_FAMILY,
    derive_rootless_task_commitment_nonces,
    rootless_integer_affine_transfer_task_pair)

repo = Path("/mnt/c/Users/aprmu/Documents/Codex/cc-cognition-next")
out = repo / "artifacts/experiments/identity-neutral-journal-recovery-20261125-request-digest-fix-v1"
key, _ = _read_private_task_commitment_key(Path(
    "/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/"
    "sentientos-data/rootless-experimental/cognition-preflight-private/"
    "20261125-identity-neutral-v4/task-commitment.key"))
history = Path(
    "/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/"
    "sentientos-data/rootless-experimental/developmental-cognition-cycles/"
    "rootless-cognition-cycle-20261124000000000009/resident-cognition/history")
selected = []
for seed in range(13688607, 13689607):
    nonces = derive_rootless_task_commitment_nonces(key, seed=seed,
        task_family_id=ROOTLESS_INTEGER_AFFINE_WIDE_TRANSFER_TASK_FAMILY)
    task = rootless_integer_affine_transfer_task_pair(seed,
        task_family_id=ROOTLESS_INTEGER_AFFINE_WIDE_TRANSFER_TASK_FAMILY,
        commitment_nonces=nonces)[1]
    task = replace(task,
        history_prompt_identity_policy="matched_cross_model_identity_omitted:v1")
    descriptor = task.public_descriptor()
    try:
        _history_probe_overlap_audit(history_root=history,
            task_probe_inputs=descriptor.get("probe_inputs"))
    except ValueError as exc:
        if str(exc) == "historical_examples_held_out_probe_overlap_detected":
            continue
        raise
    selected.append({"seed": seed, "task_digest": descriptor["task_digest"]})
    if len(selected) == 2:
        break
if len(selected) != 2:
    raise SystemExit("insufficient_nonoverlapping_seed_candidates")
with (out / "scouted_seeds.json").open("x", encoding="utf-8",
        newline="\n") as stream:
    json.dump({"schema_version": "sentientos.fresh_pair_seed_scout:v1",
        "seeds": selected, "held_out_overlap_count": 0,
        "model_loaded": False, "model_invoked": False,
        "learning_established": False, "authority": False}, stream,
        sort_keys=True, indent=2, allow_nan=False)
    stream.write("\n")
for item in selected:
    print(f"eligible_seed={item['seed']} task_digest={item['task_digest']}")
