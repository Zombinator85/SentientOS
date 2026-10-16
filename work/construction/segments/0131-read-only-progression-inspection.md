# 0131 — keep task-family progression inspection read-only

- Continues from freshly reverified source commit `5a369cbe18b630e05e9c60302ce511480688f266`, tree `38d118ba2ea985fac7789869910fc783bc532ef7`.
- Corrected the progression inspector so it reads the bounded canonical cognition checkpoint directly and validates its digest, retention bounds, and tick identities. It no longer calls `_state()`, which can reconstruct interrupted ticks or publish recovery changes.
- Completed episodes are still verified through their exact request, run, score, and invocation receipt owners. A referenced incomplete episode now returns an explicit incomplete result without changing the checkpoint; missing or conflicting references still fail. Legacy v1 checkpoints without `incomplete_ticks` remain inspectable.
- Focused suites: **164 passed, 0 failed** across resident cognition, history intervention, model replacement, objective scoring, and writeback. Changed Python compiled. Tests include a child interpreter and an interrupted scored run; receipts and model endpoints are fixture-backed, and no model improvement is claimed. Untested for production.
- Evidence: `work/construction/evidence/0131-read-only-progression-inspection.json` (SHA-256 `bf43dd68b228d605defb503fc81382209b14fbb877f8dd59095e20b8cb970dbf`).
- Next: continue testing earlier interruption windows and source-answer exclusion across a second follow-up episode; inspect any actual owner mismatch before changing production behavior.
