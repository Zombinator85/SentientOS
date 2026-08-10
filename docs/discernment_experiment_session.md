# Bounded live discernment experiment session

The experiment session closes an evidence-custody seam without merging the authority of
commissioning, calibration, or `BlindTrialCustody`. Its fixed stage chain is:

```text
external GGUF
  -> commissioning
  -> process-real identity verification
  -> session doctor
  -> explicit bounded live calibration
  -> calibration validation
  -> trial-ready handoff
  -> separate operator-controlled BlindTrialCustody action
```

Only **explicit bounded live calibration** generates model output. Commissioning,
process-real loading, doctor, session verification, and handoff are zero-generation.
Process-real loading uses the canonical `LocalModel` backend and binds the exact
`ActiveModelIdentity` to the exact matching `LocalModelAuthorityRecord`; it does not ask
the model a semantic question.

## Identity and custody

`sentientos.discernment_experiment_session.py` defines schema
`sentientos.discernment_experiment_session:v1`. `plan` independently verifies an existing
commissioning bundle and derives the session ID from the commissioning manifest digest,
model content SHA-256, byte size, sidecar digest, configuration digest, model ID,
authority-map digest, candidate index, resolved path, invocation purpose, calibration
corpus schema/digest, production/fallback posture, and session schema. Observation times,
temporary paths, and receipt ordering do not affect that semantic identity.

The explicit session root and calibration root must be external to the repository.
Session artifacts are write-once and bounded:

* `session-manifest.json`
* `commissioning-binding.json`
* `load-verification-binding.json`
* `readiness-report.json`
* `calibration-binding.json`
* `session-summary.json`
* `trial-handoff.json`

No GGUF bytes are copied. Calibration case artifacts retain their existing format under
the external calibration root; the session stores only digests, identities, summary and
repeat semantics, validation digest, and references.

## States and gates

Evidence reconstruction distinguishes `planned`, `commissioning_blocked`,
`external_prerequisite_unavailable`, `load_verified`, `calibration_eligible`,
`calibration_ready`, `calibration_degraded`, `calibration_blocked`,
`calibration_unavailable`, and `trial_handoff_ready`. States are derived from validated
artifacts rather than an editable status field. A later failure does not delete an earlier
receipt.

“Session ready” (reported as `calibration_eligible`) means that the commissioning bundle,
current model bytes/configuration, authority preview, llama.cpp dependency, durable exact
load receipt, current active identity/authority match, live-discernment readiness,
commissioning handoff, calibration corpus, and external calibration root all pass. Doctor
runs zero calibration cases and performs zero semantic generations.

`calibration_ready` additionally means the explicit live runner completed and its existing
artifacts independently reconstruct as valid, exact-identity, live evidence with the
ready classification. Neither state proves that the model is generally correct, grants
authority, adopts policy, mutates memory/goals, permits tools/actions, or creates a trial.
Missing GGUF bytes or `llama_cpp` remain `external_prerequisite_unavailable`; injected test
execution is never called process-real production evidence.

Calibration follows the existing call path:
`DiscernmentCalibrationRunner` -> `generate_participant_judgment` ->
`GovernedLocalModelInvoker` -> exact commissioned `LocalModel`. The coordinator does not
rebuild prompts, structured-output rules, repeat comparison, identity-change detection,
or case classification.

## Crash and trial boundaries

An interrupted calibration is never silently rerun. A subsequent explicit `calibrate`
validates and binds one complete existing calibration directory; partial, corrupt, or
ambiguous custody blocks. A fresh semantic run always requires the explicit `calibrate`
command, and existing artifacts are never overwritten.

Only validated live `calibration_ready` custody can emit `trial-handoff.json`. That handoff
is operator-consideration metadata. It never imports or calls `BlindTrialCustody`, creates
a trial, registers/enrolls a participant, selects or reveals an opaque slot, or submits a
judgment. The operator must separately use the authoritative blind-trial lifecycle.

All session artifacts explicitly deny provider/network invocation, tool execution,
memory/goal/action mutation, repository/Git mutation, trial creation/enrollment/
registration/submission, adoption, and authority grant.

## JSON-only CLI

Every invocation prints one JSON object. Commands are deliberately separate; no command
silently runs the full pipeline.

```bash
python scripts/discernment_experiment_session.py plan \
  --commissioning-root /external/commissioning \
  --session-root /external/session \
  --calibration-root /external/calibration

python scripts/discernment_experiment_session.py verify-load --session-root /external/session
python scripts/discernment_experiment_session.py doctor --session-root /external/session
python scripts/discernment_experiment_session.py calibrate \
  --session-root /external/session --repo-root "$PWD"
python scripts/discernment_experiment_session.py verify --session-root /external/session
python scripts/discernment_experiment_session.py handoff --session-root /external/session
```

Do not download, fabricate, substitute, or use a simulation backend to satisfy the live
path. Commission a real operator-supplied local GGUF first.
