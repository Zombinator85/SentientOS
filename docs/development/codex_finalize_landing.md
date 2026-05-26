# Codex Finalize Landing

Use `python scripts/codex_finalize_landing.py finalize` as landing authority.

Decisions: `ready_for_pr_metadata`, `repair_required_task_caused`, `manual_review_required`, `environment_blocked`, `do_not_finalize`, `finalizer_failed`.

The finalizer orchestrates focused tests, targeted mypy, baseline, matrix, gate, supervisor, docs, prompt boundary, strict audits, immutability, and hygiene with optional strict-audit repair and generated-artifact cleanup.
