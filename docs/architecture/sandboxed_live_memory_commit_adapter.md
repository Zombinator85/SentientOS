# Sandboxed Live Memory Commit Adapter

`sentientos/sandboxed_live_memory_commit_adapter.py` implements the `sandboxed_live_memory_commit_adapter` capability as a deterministic, sandbox-only metadata adapter. It consumes explicit Live Commit Safety Interlock evidence plus sandbox commit candidates and can write deterministic JSON artifacts only under a caller-provided sandbox root.

## Boundary and authority

The adapter is not a real live-memory writer. Successful packets, receipt manifests, and rollback manifests explicitly state that sandbox commit is not:

- a real memory write, deletion, or purge;
- a live index mutation;
- policy, truth, consent, or authority;
- prompt assembly, action execution, or external disclosure.

A future real live-memory adapter and future real memory-root admission remain required before any real memory write, delete, purge, or live index mutation can be considered.

## Required safety-interlock matching

Every candidate must reference matching safety-interlock evidence:

- a safety-interlock packet with at least one record and a packet digest;
- a ready safety-interlock decision such as `live_commit_adapter_consideration_eligible`, warning, operator-review, rejection, or noop decisions;
- candidate `claimed_safety_interlock_digest` equal to the packet digest;
- candidate `claimed_safety_interlock_decision` equal to the packet decision;
- candidate scope keys aligned with the safety-interlock scope keys.

Missing, invalid, not-ready, digest-mismatched, decision-mismatched, and scope-mismatched evidence blocks with `sandbox_commit_blocked`.

## CLI

`scripts/build_sandboxed_live_memory_commit_adapter.py` exposes:

- `build-default` — prints the default deny-by-default policy.
- `evaluate` — evaluates input and writes nothing.
- `validate` — validates a policy or default policy.
- `summarize` — prints status, digest, packet digest, counts, and finding codes.
- `inspect-fixture` — loads a fixture from `tests/fixtures/sandboxed_live_memory_commit_adapter/`.
- `write-sandbox-artifacts` — requires explicit `--sandbox-root` and writes deterministic JSON only under that safe sandbox root.

Blocked, invalid, or failed outcomes exit nonzero. `write-sandbox-artifacts` also exits nonzero when `--sandbox-root` is omitted, unsafe, or when input evaluation blocks.

## Sandbox artifacts

When evaluation succeeds and `write-sandbox-artifacts` is invoked with a safe sandbox root, the adapter writes:

- one deterministic sandbox artifact for each candidate record at its safe relative path;
- `sandbox_receipt_manifest.json`, a sandbox-only manifest of emitted artifacts and non-authority statements;
- `sandbox_rollback_manifest.json`, a sandbox-only rollback manifest that describes removal of sandbox artifacts only and confirms real memory was not mutated;
- `sandbox_commit_packet.json`, the deterministic packet/report output.

The writer rejects absolute candidate paths, `..` traversal, real-memory-root path claims, and sandbox roots whose resolved path appears to target real/live memory.

## Blocked claims

The adapter blocks live write, live delete, live purge, live index mutation, prompt materialization, action execution, external disclosure, authority smuggling, consent smuggling, policy smuggling, truth smuggling, raw/private/media/secret/prompt payload leakage, unsafe sandbox roots, real-memory-root claims, path traversal, and scope mismatch.

## Validation proof points

The test suite proves:

- evaluate mode is deterministic and writes no files;
- `write-sandbox-artifacts` writes only under the sandbox root;
- receipt and rollback manifests are deterministic and sandbox-only;
- real live-memory root claims and path traversal are blocked;
- safety-interlock digest and decision mismatch block;
- unsafe live mutation, prompt, action, disclosure, smuggling, leakage, and scope claims block;
- noop behavior is deterministic and non-mutating.

## Forbidden next steps

The capability remains forbidden from real live-memory write/delete/purge, live index mutation, prompt assembly, live context retrieval, action ingress, safety-interlock bypass, and external disclosure. These remain explicitly listed in packet and manifest `forbidden_next_steps` for reviewer visibility.
