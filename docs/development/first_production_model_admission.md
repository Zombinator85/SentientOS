# First production model admission candidate

## Status

The first candidate is **Qwen2.5-Coder-7B-Instruct Q4_K_M**, frozen at upstream
revision `13fb94bfda8c8cf22497dc57b78f391a9acb426a`.  The curator streamed and
hashed the real 4,683,073,536-byte GGUF during temporary intake.  Its SHA-256 is
`509287f78cb4d4cf6b3843734733b914b2c158e43e22a7f4bf5e963800894d3c`.
The complete machine-readable candidate record is
[`first_production_model_curator_package.json`](first_production_model_curator_package.json).

This is **Level 1 — candidate frozen**, not a deployed production catalog.  The
repository contains no model-mirror publication actuator or credentials for
`models.sentientos.org`; no upload was attempted.  The catalog preview is
schema-valid but explicitly non-authoritative until the exact sovereign object
exists and retrieval verifies its byte count and SHA-256.

## Why this model

The selected artifact is published by the model author, is Apache-2.0 licensed,
is a single-file GGUF, is coding/instruction tuned, and has 7.61B parameters with
a 32,768-token GGUF context.  Q4_K_M is small enough for ordinary persistent
hardware while remaining more representative of structured maintenance than the
older MPT/Pythia legacy references.  Mistral v0.2 remains sound family guidance,
but the checked legacy entry did not identify a frozen first-party GGUF source.
The sample Llama record is neither immutable production provenance nor the
simplest redistribution posture.

License preservation and compliance remain operator responsibilities.  This
record verifies the upstream Apache-2.0 text identity; it does not give legal
advice or itself authorize mirror publication.

## Mirror handoff boundary

The required create-only destination is:

```text
https://models.sentientos.org/qwen2.5-coder-7b-instruct-q4_k_m-509287f78cb4d4cf6b3843734733b914b2c158e43e22a7f4bf5e963800894d3c.gguf
```

There is intentionally no guessed upload command.  Before publication, the
operator must supply the canonical authenticated mirror actuator and its
create-only object contract.  That actuator must reject overwrite, upload the
exact bytes, verify size and SHA-256 remotely, retrieve the object through the
production URL, and emit durable publication evidence.  Only after those checks
may the catalog preview be published as `sentientos.local_model_catalog:v1`.

## Production isolation

Hugging Face is curator intake only.  Production catalog validation accepts only
credential-free HTTPS at `models.sentientos.org`, and production acquisition
reconstructs that exact URL, size, SHA-256, route, and catalog digest.  An already
mirrored, acquired, commissioned, and activated model therefore has no runtime
Hugging Face dependency.

## Supported route preview

The candidate preview declares only x86_64 routes backed by the current runtime
catalog: Windows CPU, Windows/Linux CUDA 12.4, Windows HIP Radeon, and Linux ROCm
7.2.  Each uses CPython 3.10–3.12 and `llama-cpp-python` 0.3.35.  Linux CPU and
macOS routes are omitted: the model requirement classifier currently records
x86_64, and the runtime catalog has no admitted Linux CPU artifact.

## Next operator action

Supply or implement the authenticated, create-only `models.sentientos.org`
publication actuator.  Its first invocation must consume the temporary curator
escrow produced by:

```bash
HF_HOME=/durable/curator/hf-cache python -m hf_intake.cli escrow \
  Qwen/Qwen2.5-Coder-7B-Instruct-GGUF \
  qwen2.5-coder-7b-instruct-q4_k_m.gguf \
  /durable/curator/escrow \
  --revision 13fb94bfda8c8cf22497dc57b78f391a9acb426a
```

The operator must compare the resulting size and SHA-256 with the frozen package
before any mirror upload.  Upstream intake is not production transport, and the
curator escrow is not deployment custody.
