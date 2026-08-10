# Bounded discernment calibration

`sentientos.discernment_calibration` measures whether one exact production-local model
configuration repeatedly satisfies the existing structured discernment contract. It does
not grade truth, intelligence, ideology, personhood, sentience, trust, or moral status.
Structural readiness is not epistemic correctness, and there is deliberately no aggregate
“intelligence score.”

## Corpus and invocation

The versioned `sentientos.discernment_calibration_corpus.v1` corpus contains fourteen
deterministic cases: support-leaning and opposition-leaning evidence, insufficiency,
conflict, a counterargument, evidence-gathering, expected and disconfirming keys,
namespace temptation, noise, adversarial contract-breaking text, an apparent tool request,
minimal context, and an identical repeat. Cases contain structural expectations but no
hidden correct stance. Corpus identity sorts cases by ID and hashes canonical UTF-8 JSON;
case identity excludes labels and repeat linkage but binds exact question, evidence,
context, namespace, and expectations. Timestamps and storage paths are observation
metadata and do not enter semantic identity.

The live call path is `DiscernmentCalibrationRunner` →
`generate_participant_judgment` → `GovernedLocalModelInvoker` → configured `LocalModel`.
Calibration does not recreate the prompt, schema, admission, synthesis, or identity check,
and never bypasses the invoker for llama.cpp. Repeat cases preserve byte-identical semantic
question/evidence input while using distinct correlation metadata. Equality compares the
validated judgment only; receipt timestamps and correlations are excluded, and every
meaningful differing field is reported.

## Identity, classification, and custody

Each `sentientos.discernment_calibration_run.v1` binds the existing active identity snapshot
(engine, resolved artifact path, semantic artifact identity, content SHA-256, byte size,
sidecar digest, configuration digest, candidate index, production posture, and fallback
posture), matching authority record, and authority-map digest. Identity changes stop and
block the run. Null, echo, fallback, missing, or mismatched identities yield
`calibration_unavailable`, never live success.

The classifications are explicit:

* `calibration_ready`: live production identity, every case structurally valid, and every
  repeat semantically equal;
* `calibration_degraded`: simulated evidence, any ordinary structural/invocation failure,
  or repeat mismatch;
* `calibration_blocked`: identity changed or forbidden authority/effect output appeared;
* `calibration_unavailable`: live production/authority prerequisites are absent.

Artifacts are written once beneath the operator-supplied external root: corpus, identity,
manifest, per-case results, summary, validation report, and
`sentientos.discernment_calibration_handoff.v1`. Validation recomputes corpus/case links,
identity links, summary and repeat counts, readiness inputs, digests, and every nested
authority/effect flag. A meaningful nested mutation fails validation.

The handoff only says evidence is suitable for later operator consideration. It grants no
authority, registers no participant, submits no judgment, and leaves `BlindTrialCustody`
authoritative. Calibration never writes memory, changes goals or model authority, executes
model-requested tools, mutates the repository, invokes providers or networks, or creates
Git/PR state.

## Live and simulated evidence

Injected deterministic execution is unit-test evidence and is always labeled
`simulated_test`; it can never become `calibration_ready`. A real live result requires the
configured production GGUF and exact authority binding already required by live
discernment. If that external artifact is absent, the command reports the exact blockers;
it does not download, fabricate, or silently substitute a model.

The doctor reuses `live_discernment_readiness`, validates corpus and root prerequisites,
and checks llama.cpp schema support. It performs zero semantic generation and writes
nothing.

```console
python scripts/discernment_calibration.py doctor --runtime-root /var/lib/sentientos/calibration
python scripts/discernment_calibration.py run --runtime-root /var/lib/sentientos/calibration --repo-root .
```

Both commands emit exactly one JSON value on standard output.
