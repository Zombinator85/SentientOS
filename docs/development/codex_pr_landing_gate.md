# Codex PR landing gate

`sentientos/codex_pr_landing_gate.py` is the deterministic metadata-only final pre-`make_pr` gate.

It composes:
- PR metadata contract checks,
- PR validation evidence checks,
- validation matrix lane contract checks.

CLI: `python -m scripts.codex_pr_landing_gate verify|build-body|gate`.
