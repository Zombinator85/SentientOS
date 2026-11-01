# Rootless experimental local-model inference

This path supports one explicitly bounded, real local-model inference from a
Codex Cloud workspace. It reuses the verified `llama-cpp-python` installation,
the isolated `ExactRuntimeLocalModel` worker, model identity projection,
`GovernedLocalModelInvoker`, and the ordinary `LOCAL_MODEL_INFERENCE` control
plane admission.

It is deliberately separate from production commissioning and from the existing
developmental model-replacement serving path. It does not open or initialize an
`InstallationStateRegistry`, and it never writes under `/var/lib/sentientos`.
Its intents, attempts, invocation receipts, and result receipts are written under
`/workspace/sentientos-data/rootless-experimental/`. The path rejects roots
outside `/workspace` and rejects symlinked custody paths.

Every intent and result records:

- `experimental_rootless: true`, `ephemeral_environment: true`, and
  `production_authority: false`;
- ineligibility for production commissioning, production serving, native
  subagent observations, and Astra results;
- exact model source, pinned Hugging Face revision, license and license-file
  digest, model card digest, artifact size and SHA-256;
- exact verified runtime installation, import, and CPU-backend receipt digests;
- the exact prompt and response, invocation receipt, loaded model identity,
  control-plane admission reference, timestamps, CPU time, and worker peak RSS.

The smoke budget is fixed at context 512, CPU only (`n_gpu_layers=0`), at most
five threads, at most 16 generated tokens, one invocation per correlation, and a
90-second timeout. There are no tools, provider requests, repository changes,
memory writeback, model activation, or serving lifetime.

An execution intent is write-once. The runner creates an attempt marker before
loading the worker. It will not replay an intent if an attempt or final receipt
already exists. If a call fails after backend entry, preserve that attempt and
reconcile it from its invocation custody rather than retrying automatically.

## Prepare and execute

The caller supplies a model-artifact manifest in the experimental root and the
three verified runtime receipts. Preparing an intent verifies all receipt
digests, the worker interpreter, the source/license bindings, and model bytes;
it does not load the model or infer.

```console
python scripts/run_rootless_experimental_local_model.py prepare \
  --model-manifest /workspace/sentientos-data/rootless-experimental/model-artifact-manifest.json \
  --installation-receipt <verified-installation-receipt> \
  --import-receipt <verified-runtime-import-receipt> \
  --backend-receipt <verified-cpu-backend-receipt> \
  --prompt '<exact prompt>'
```

Review the resulting intent and pass its exact digest to `execute`:

```console
python scripts/run_rootless_experimental_local_model.py execute \
  --model-manifest /workspace/sentientos-data/rootless-experimental/model-artifact-manifest.json \
  --installation-receipt <verified-installation-receipt> \
  --import-receipt <verified-runtime-import-receipt> \
  --backend-receipt <verified-cpu-backend-receipt> \
  --intent <workspace-custodied-intent.json> \
  --confirm-intent-digest <exact-intent-digest>
```

The runner rechecks the artifact and runtime receipts immediately before loading,
requires the loaded worker identity to match the verified artifact and explicit
`rootless_experimental` posture, and calls the ordinary local inference owner.
The runtime control plane must admit the exact call. A denial does not call the
model.

## Evidence boundary

The rootless receipt uses the distinct
`sentientos.rootless_experimental_inference_receipt:v1` schema and lives outside
canonical installation custody. Production commissioning continues to require
its hardened v3 receipt, canonical installation handle, current authoritative
catalog proof, hardened acquisition receipt, and independent admissions. A
rootless result therefore cannot satisfy production commissioning, production
serving, or activation consumers. Production installation and authority
contracts remain unchanged.

This path demonstrates a bounded local-model response in an ephemeral
engineering workspace. It does not establish a persistent installation,
production deployment, model identity beyond the recorded artifact/runtime,
learning, improvement, consciousness, or general capability.

The separate resident-cognition experiment uses the same verified rootless
runtime with preregistered evidence-correction and unsupported-pressure
conditions. Its limits, scoring result, and separately sealed evidence are
documented in the [rootless experimental epistemic series](rootless_experimental_epistemic_series.md).

## Codex Cloud smoke execution

On 2026-11-01, the path completed one CPU-only Qwen2.5-0.5B-Instruct GGUF
smoke inference in the managed workspace. The exact prompts, both attempt
records, runtime receipts, model source/license files, invocation receipts,
governor records, result receipt, and a per-file SHA-256 custody manifest are
preserved in
[`evidence/rootless_experimental_local_model_smoke_2026-11-01/README.md`](evidence/rootless_experimental_local_model_smoke_2026-11-01/README.md).
The first attempt deferred before generation because an auxiliary trust-epoch
path defaulted to read-only `/glow`; that attempt is retained. A scoped routing
fix then allowed the normal governor to admit a new one-shot intent. The
successful answer was `ROOTLESS-SMOKE-OK` (457 ms invocation latency, 642,752,512
bytes worker peak RSS). Both observations are explicitly non-production, and
the successful one does not establish Astra identity or production model
commissioning.
