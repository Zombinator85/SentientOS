# Ethics, Governance & Safety Controls

SentientOS v1.2.0-beta emphasises transparent autonomy, human oversight
and explicit governance tooling. This document summarises the key safety
features and how operators interact with them.

## Council Oversight

* **Council membership** is configured in `config.runtime.council`.
* The runtime records vote outcomes, quorum state and tie-breaker notes.
* Sensitive browser or GUI actions trigger council confirmation. If the
  operator does not approve (CLI prompt or dashboard) the action is
  vetoed with `council_veto` and the audit log notes the rejection.

## Panic Flag

* Persistent panic state lives in `glow/state/panic.json`.
* Toggle via:
  * `make panic-on`
  * `make panic-off`
  * `python tools/panic_flag.py status`
* When panic is active, GUI and browser actuators refuse to execute and
  log `reason: panic` entries to the autonomy action log.

## Audit & Transparency

* Every embodied action (GUI, browser, council decision, panic toggles)
  appends JSON lines to `logs/autonomy_actions.jsonl`.
* Inspect via `make audit-log` which renders the last 50 entries.
* The FastAPI endpoint `/admin/status/autonomy` surfaces:
  * Recent actions grouped by module
  * Council vote history
  * Panic status and safety budgets (GUI + social automation)

## Persistence & Continuity

* Mood state is restored on startup when `persistence.restore_mood` is
  enabled. Decay factor controls smoothing of the stored vector.
* Reset persisted mood with `make reset-mood`.

## Rate Limits & Budgets

* Social automation enforces daily action budgets and a domain allowlist.
* GUI controller rejects unsafe text entry (password, token, secret).
* OCR automatically throttles when CPU utilisation exceeds 85%.
* TTS rate limits characters per minute to prevent runaway output.

## Logging & Metrics

* Governance events increment Prometheus counters exposed via
  `/admin/metrics` (council votes, panic toggles, audit requests).
* Readiness and diagnostics produce machine readable reports under
  `glow/reports/` for compliance review.

## Operator Checklist

1. Run `make autonomy-readiness` prior to enabling autonomy features.
2. Review `/admin/status/autonomy` after each council action.
3. Keep `logs/autonomy_actions.jsonl` under versioned retention for
   cross-team audits.
4. Reset mood and panic state when transferring the runtime between
   operators or hardware.

