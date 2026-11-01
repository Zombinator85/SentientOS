# Rootless experimental local-model smoke evidence

This bundle captures one genuine, bounded local inference through SentientOS in
the Codex Cloud managed workspace. It is an engineering smoke test, not a
cognition evaluation or preregistered epistemic observation.

The `success/` files contain the sealed intent, attempt marker, invocation and
outer receipts, and control-plane/governor evidence. The `blocked/` files retain
the earlier no-output attempt; it deferred before generation because the
governor's Pulse trust-epoch state defaulted to read-only `/glow`. The follow-up
used a new intent after routing that auxiliary state to the run-scoped writable
workspace. No uncertain model transmission was replayed.

`runtime/` contains the exact verified installation, import, and CPU-backend
receipts. `model-artifact-manifest.json`, `model-card/README.md`, and
`model-card/LICENSE` bind the public, pinned Qwen2.5-0.5B-Instruct GGUF source,
Apache-2.0 license, size, and SHA-256. The 491,400,032-byte model weights are
not included; their pinned public source and digest are recorded in the
manifest. `observation-summary.json` gives a compact report, while
`custody-manifest.json` lists SHA-256 and size for every other file in this
directory.

The successful response is `ROOTLESS-SMOKE-OK`, generated with CPU-only
`llama-cpp-python 0.3.35`, 512 context tokens, five threads, at most 16 output
tokens, and a 90-second call budget. This evidence is marked rootless,
ephemeral, and non-production. It grants no production commissioning, serving,
activation, Astra, or native-subagent status.
