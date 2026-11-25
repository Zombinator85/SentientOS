from pathlib import Path
from dataclasses import replace
import sys

sys.path.insert(0, "/mnt/c/Users/aprmu/Documents/Codex/cc-cognition-next")
from scripts.preflight_resident_historical_examples_pair import (
    _history_probe_overlap_audit, _read_private_task_commitment_key)
from sentientos.developmental_model_replacement_experiment import (
    ROOTLESS_INTEGER_AFFINE_WIDE_TRANSFER_TASK_FAMILY,
    derive_rootless_task_commitment_nonces,
    rootless_integer_affine_transfer_task_pair)

key, _ = _read_private_task_commitment_key(Path(
    "/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/"
    "sentientos-data/rootless-experimental/cognition-preflight-private/"
    "20261125-identity-neutral-v4/task-commitment.key"))
history = Path(
    "/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/"
    "sentientos-data/rootless-experimental/developmental-cognition-cycles/"
    "rootless-cognition-cycle-20261124000000000009/resident-cognition/history")
selected = []
for seed in range(13688605, 13689605):
    nonces = derive_rootless_task_commitment_nonces(
        key, seed=seed,
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
    selected.append((seed, descriptor["task_digest"]))
    print(f"eligible_seed={seed} task_digest={descriptor['task_digest']}")
    if len(selected) == 2:
        break
if len(selected) != 2:
    raise SystemExit("insufficient_nonoverlapping_seed_candidates")
