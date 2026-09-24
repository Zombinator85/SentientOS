# Resident cognitive model serving system rehearsal

This repository-native harness exercises the production activation verifier,
`ResidentCognitiveModelServingController`, `ResidentCognitiveServingInvoker`,
`GovernedLocalModelInvoker`, `ResidentDevelopmentalCognitionOwner`, developmental
writeback, and (for coexistence) `ProductionServingController`. It requires an empty,
caller-supplied root and never defaults to installation custody.

```bash
PYTHONPATH=. python scripts/run_resident_cognitive_model_serving_rehearsal.py run --scenario happy --root /tmp/sentientos-resident-serving-happy --summary
PYTHONPATH=. python scripts/run_resident_cognitive_model_serving_rehearsal.py run --scenario activation-change --root /tmp/sentientos-resident-serving-activation-change --summary
PYTHONPATH=. python scripts/run_resident_cognitive_model_serving_rehearsal.py run --scenario production-chat-coexistence --root /tmp/sentientos-resident-serving-coexistence --summary
```

## Evidence and scenarios

Every scenario and verification artifact uses `evidence_posture = synthetic_rehearsal`.
The schemas are `sentientos.resident_cognitive_model_serving_rehearsal:v1` and
`sentientos.resident_cognitive_model_serving_rehearsal_verification:v1`. Synthetic
catalog, commissioning, activation, admission, and worker evidence cannot become
production evidence or a production experimental trial.

The **happy** scenario establishes exact activation A with zero establishment
inference, then supplies the serving-backed invoker to the real developmental cognition
owner. The owner performs separately admitted local inference and writeback before the
resident worker is closed. The **activation-change** scenario activates B outside the
resident controller, observes A invalidation and one close, and proves there is no B
construction, second serving admission, fallback, or automatic rebind. The
**production-chat-coexistence** scenario establishes both real serving controllers from
the same activation and proves their admission, session, receipt, close, and invalidation
custody remain independent.

The bundle contains `scenario.json`, `manifest.json`, `verification.json`, `summary.json`,
and `README.md`; production owners additionally write their ordinary evidence beneath
the isolated installation and cognition roots.

## Configuration binding and nonclaims

Ordinary startup resident-serving configuration remains bound to one serving operation,
one exact expected activation-state digest, and one configuration digest. A future
A-to-B-to-A experiment therefore needs a separately governed, protocol-bound
transition-stage serving binding; it must not silently reuse the A-bound startup config.
This rehearsal grants no transition authority, does not select a production model, does
not follow activation automatically, and changes no production chat semantics.

Run the resident cognitive serving system rehearsal before modifying resident cognitive
serving, sentientosd resident model composition, or resident cognitive-model transition
logic. Repair task-caused rehearsal regressions before landing. Codex, rather than the
human operator, runs this preflight and inspects its generated artifacts.
