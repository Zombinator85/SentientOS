from pathlib import Path
import json
import sys

sys.path.insert(0, "/mnt/c/Users/aprmu/Documents/Codex/cc-cognition-next")
from analysis.audit_matched_task_commitment_prompt_parity import audit_pair, _read_json
from analysis.create_matched_history_record_allowlist import create_allowlist, _digest

repo = Path("/mnt/c/Users/aprmu/Documents/Codex/cc-cognition-next")
source = repo / "artifacts/experiments/identity-neutral-journal-recovery-20261125-request-digest-fix-v1"
out = repo / "artifacts/experiments/identity-neutral-journal-recovery-20261125-observation-scoped-v1"
seeds = json.loads((out / "scouted_seeds.json").read_text())["seeds"]
cycle = Path(
    "/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/"
    "sentientos-data/rootless-experimental/developmental-cognition-cycles/"
    "rootless-cognition-cycle-20261124000000000009")
audit_path = source / "parity_13688607.json"
pair_path = source / "matched_pair_13688607.json"
left = source / "hermes_13688607_preflight.json"
right = source / "qwen_13688607_preflight.json"
reconstructed = audit_pair(receipt_path=pair_path, left_path=left,
    right_path=right,
    left_verification_path=Path(str(left) + ".verified.json"),
    right_verification_path=Path(str(right) + ".verified.json"),
    cycle_root_path=cycle)
saved, _ = _read_json(audit_path)
if saved != reconstructed:
    raise SystemExit("source_parity_audit_reconstruction_mismatch")
for item in seeds:
    value = create_allowlist(audit_path=audit_path)
    semantic = {key: entry for key, entry in value.items()
        if key != "allowlist_digest"}
    semantic["task_digest"] = item["task_digest"]
    value = {**semantic, "allowlist_digest": _digest(semantic)}
    path = out / f"allowlist_{item['seed']}.json"
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, indent=2,
            ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    print(f"allowlist_written seed={item['seed']} digest={value['allowlist_digest']}")
