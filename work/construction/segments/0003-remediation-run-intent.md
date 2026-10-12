
## 2026-10-12 checkpoint — persist remediation intent before commands

- Continued from exact remote `d6cf835e0c7861789f089f7012a15d5850796c01`, tree `e7c0ca087d73bcf705ad5a2926d8ef4fffefc662`.
- The remediation runner now publishes a bounded immutable run intent before the first command; the final report binds the intent digest. Restart discovery treats an orphan intent as incomplete/invalid and both automatic retry and direct runner re-entry fail closed. Historical reports without intents remain compatible when no new intent claims that run.
- Focused owner-path suites: 25 passed. Additional quarantine-remediation cases: 4 passed. The old hand-written completed-run fixture still fails safely; the actual owner-produced clear positive control passes. See `work/remediation_run_intent_acceptance.json`.
- Changed Python compiled; `git diff --check` passed. POSIX custody was exercised hermetically; Windows durability and real remediation execution remain unverified.
- Next: determine the minimum complete hosted lifecycle from current source and select the next runtime composition gap; update the stale atlas maturity synthesis only as a later source-bound snapshot, never rewrite the frozen census.
