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

## Experimental limitation

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

The requested placement setting and its software checks are established. Real
Hermes cognition on GPU remains unverified until an Ollama runtime with a
GPU-capable inference library is available. Do not retry against the same
CPU-only runtime. Any later attempt must use a new seed and protocol digest
binding its configured GPU layer count; prior protocols and failed runs must
not be reused or overwritten.
