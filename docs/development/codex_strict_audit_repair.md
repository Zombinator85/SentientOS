# Codex strict audit repair

Use `python scripts/codex_strict_audit_repair.py diagnose --summary` to classify strict audit failures.
Use `python scripts/codex_strict_audit_repair.py repair --allow-runtime-chain-reseal --summary` only for known generated runtime chain drift involving `pulse/audit/privileged_audit.runtime.jsonl`.
Always rerun `python verify_audits.py --strict` and `python scripts/audit_immutability_verifier.py`.
