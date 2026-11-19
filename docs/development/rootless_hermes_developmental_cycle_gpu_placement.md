# Rootless Hermes developmental-cycle GPU placement

## Milestone goal and acceptance

Make the rootless developmental cognition runner request a configured, bounded
GPU layer count through the production Ollama session path, while retaining the
generic epistemic session's CPU-only default. The setting must be rejected
before experiment setup when malformed or outside 1–128, and the requested
placement must be retained in run and inference resource evidence.

Acceptance requires focused tests for configuration bounds, developmental
session forwarding, unchanged generic CPU defaults, and evidence recording. A
real-model follow-up is a separate, newly preregistered experiment. It must
verify actual GPU residency and governed release; the requested layer count by
itself is not evidence that the model used the GPU.

## Finding

The developmental cycle's resource guard already requires observed GPU model
placement and stops on CPU fallback. However,
`RootlessExperimentalOllamaDevelopmentalSession` previously omitted the
underlying session's `gpu_layers` argument, leaving its default at zero. The
runner therefore requested CPU-only inference while requiring GPU placement.
The generic `RootlessExperimentalOllamaEpistemicSession` keeps its existing
zero-layer default.

## Implementation

The developmental session now forwards an explicit bounded layer count. The
cycle runner reads `SENTIENTOS_HERMES_GPU_LAYERS` (default `99`), accepts only
ASCII decimal values from 1 through 128, and records the configured request in
the preregistration, initial resource sample, per-inference resource records,
and terminal result or failure record. This records intended placement; runtime
telemetry remains responsible for establishing observed placement.

## Experiments and current limitation

The first 2026-11-19 attempt for task family
`rootless_integer_affine_transfer_low_range_v5` stopped before model inference
after observing CPU-only placement. Its immutable failure record is retained in
the external experiment custody. It does not demonstrate cognition behavior.

A second one-shot attempt used source commit `2b05ac7003e029d1e7b802183a34a7ab2bcf795b`,
seed `20261120`, protocol digest
`742ccee197d4c4a2ec1550cb422dfc2f8fa92e804ebffdf222e119715d2e9ecf`, and a
requested layer count of 99. The run again observed `size_vram_bytes: 0` and
`cpu_only`, timed out without a model response, then recorded a successful
governed unload. No cognitive behavior was measured. The Ollama server log
identified its active inference backend as `library=cpu`; the model load record
reported `layers.offload=0`. This supports an environment/runtime limitation,
not a failure to forward the requested setting. The run's immutable failure
artifact is `cycle-failure.json` in the private experimental custody.

The Windows Ollama 0.12.9 runtime exposed only `library=cpu`. An isolated
official Ollama 0.40.16 payload was then verified without replacing the
installed application. Its startup log detected the RTX 3060 through CUDA, and
`ollama ps` reported the bound 14B Hermes model at `100% GPU`, context 8192.
The runtime packages and model were hash-bound in the external protocol and
experiment custody.

The Windows follow-ups exposed two separate boundaries. Seed `20261122` reached
the owner with caller-asserted synthetic proprioception, but the prompt asked
about the “current” pose; the existing freshness rule correctly changed the
answer to a request for a fresh observation. The prompt now explicitly frames
this as hypothetical planning and labels the proprioception unverified. The
freshness rule was not weakened. Seed `20261123` produced a lineage-verified
`reach` proposal with a consistent `reach` prediction, then stopped because the
secure consequence store does not support Windows descriptor-relative
publication.

Seed `20261124` ran commit `fbe942cb4a6cd125354017834e97010f05d37616` in an
isolated Ubuntu 24.04 WSL checkout, with experiment custody on ext4 and a
separate copy of only the bound Hermes model. The protocol digest was
`ee2b7b53d7fcecb395c8975f07b28e956d5eda310cb892d10da4ab6089142afd`. Runtime
telemetry again observed GPU offload. The pre-action record contains one
source-linked synthetic fact, a verified response lineage, the proposal
`reach` with prediction `reach`, and `action_executed: false`. The synthetic
action was simulated for the fixture; no production action occurred.

The cycle then stopped during governed developmental writeback with
`developmental_inference_not_completed`. The inference receipt records
`runtime_governor:deferred_background_inference_under_host_pressure`. Resource
samples showed `disk_pressure` and `sensor_unavailable`; a later sample also
showed `gpu_pressure`. The runtime governor was preserved as the boundary, and
the experiment did not reach the history-present/withheld/restored comparison.
Governed unload confirmed the model was no longer resident, and GPU memory
returned near its pre-run level. This demonstrates GPU placement and one
synthetic, evidence-linked proposal, not experience retention, learning,
transfer, or improved later decisions.

### Pressure deferral recovery

The pressure-limited run also exposed an opaque handoff: a governor-deferred
writeback surfaced as the same generic incomplete-inference error as other
failures, even though the selected fact identities were not marked processed.
The resident owner now recognizes only the exact governed host-pressure
deferral receipt, completes that tick with an explicit deferred status and
selection identity, and leaves the source facts eligible for a later distinct
tick if the same immutable fact identities are present in a later snapshot. It
does not retain unadmitted evidence payloads in composition state, replay the
deferred tick, or weaken any governor decision.
Malformed output, other denials, and unrelated writeback failures remain
fail-closed. A controlled CPU fake verifies that a deferred tick does not
consume its facts and a subsequent tick writes a record bound to those same
fact identities after an owner restart and a later snapshot with changed
observation times. This validates the retry handoff in software; it does not
remove host pressure or substitute for repeating the full real-model transfer
comparison under a newly preregistered protocol.

The current blocker is a pressure-compliant run of the full developmental
writeback and transfer comparison. Any further attempt requires a new
protocol and seed; prior protocols and failure records are immutable and must
not be retried or overwritten.
