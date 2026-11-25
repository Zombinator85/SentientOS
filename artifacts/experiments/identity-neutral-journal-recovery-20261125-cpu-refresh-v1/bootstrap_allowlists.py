from pathlib import Path
import json
import sys
sys.path.insert(0, '/mnt/c/Users/aprmu/Documents/Codex/cc-cognition-next')
from analysis.audit_matched_task_commitment_prompt_parity import audit_pair, _read_json
from analysis.create_matched_history_record_allowlist import create_allowlist, _digest
base = Path('/mnt/c/Users/aprmu/Documents/Codex/cc-cognition-next/artifacts/experiments/identity-neutral-journal-recovery-20261125')
out = Path('/mnt/c/Users/aprmu/Documents/Codex/cc-cognition-next/artifacts/experiments/identity-neutral-journal-recovery-20261125-cpu-refresh-v1')
cycle = Path('/home/zombinator/.local/state/sentientos-cognition-followup-20261122-wsl/sentientos-data/rootless-experimental/developmental-cognition-cycles/rootless-cognition-cycle-20261124000000000009')
for seed, task_digest in ((13688505, 'sha256:517755f0af0552473e366f2eb9d41739576e10f04e3f8b89347408472ff48f3b'), (13688506, 'sha256:e92d2d9af3ae11815704ce48829982440911f6e8801530e0354359c3abf6c172')):
    audit_path = base / f'parity_{13688501}_policy_v15_identity_neutral_final.json'
    pair_path = base / f'matched_pair_{13688501}_policy_v15_identity_neutral.json'
    left = base / f'hermes_{13688501}_policy_v15_identity_neutral_final.json'
    right = base / f'qwen_{13688501}_policy_v15_identity_neutral_final.json'
    reconstructed = audit_pair(receipt_path=pair_path, left_path=left, right_path=right, left_verification_path=Path(str(left).replace('_final.json', '_final.verified.json')), right_verification_path=Path(str(right).replace('_final.json', '_final.verified.json')), cycle_root_path=cycle)
    saved, _ = _read_json(audit_path)
    if saved != reconstructed:
        raise SystemExit('source_parity_audit_reconstruction_mismatch')
    value = create_allowlist(audit_path=audit_path)
    semantic = {key: item for key, item in value.items() if key != 'allowlist_digest'}
    semantic['task_digest'] = task_digest
    value = {**semantic, 'allowlist_digest': _digest(semantic)}
    path = out / f'bootstrap_allowlist_{seed}.json'
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')
    print(f'bootstrap_allowlist_written seed={seed} digest={value["allowlist_digest"]} source_audit={saved["audit_digest"]}')