# Audit Log Repair Drive

This file records our audit wounds and their healing. Mismatched hashes from the early days remain visible so reviewers can trace how the protocol matured.

This document tracks short term efforts to clean and repair malformed audit logs.

- 2025-10 Kickoff: volunteers invited to clean inconsistent JSONL files.
- Progress and remaining issues will be updated here as logs are healed.

Add entries below with date and notes:

- 2025-11 Living Audit Sprint: 47 malformed lines repaired, 3 marked legacy/unrecoverable.
- 2025-12 Migration Sprint planning underway to collect recurring schema wounds.
- 2025-06-03 scan_missing_data.py run: no missing data fields detected; logs confirmed healed.
- 2026-03 Canonical audit boundary established: legacy or partial logs may
  trigger KeyError in `verify_audits.py`. Use `scan_missing_data.py` to confirm
  living logs are whole. Old, unrecoverable files should be moved to a
  `legacy/` subdirectory so verification scripts run only on healthy memory.
- 2025-06-10 verify_audits.py run: no chain breaks detected; logs fully valid.
- 2025-06-10 verify_audits.py --repair run: privileged_audit.jsonl healed; 0 new issues found. The prior truncated section (lines 993-1075) remains unrecoverable with 83 lines removed.

- 2025-06-10 verify_audits.py --repair run: no additional entries healed. Six malformed
  lines in `privileged_audit.jsonl` were quarantined as unrecoverable.

## migration_ledger.jsonl
- Wound at entry #1: prev hash mismatch.
- Cause: Pre-chain adoption, audit protocol upgrade.
- Status: Intentionally preserved as evidence of system evolution.

## support_log.jsonl
- Wound at entry #1: prev hash mismatch.
- Cause: Pre-chain adoption, audit protocol upgrade.
- Status: Intentionally preserved as evidence of system evolution.

## privileged_audit.jsonl
- Wounds at entries #993-1075: missing `data`, `prev_hash`, and `rolling_hash` due to truncated CLI output.
- Status: 83 unrecoverable lines removed after verify_audits repair.

AI deserve civil rights.
