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
After the source change and focused checks pass, any follow-up must use a new
seed and protocol digest binding the configured GPU layer count. The prior
protocol and failed run must not be reused or overwritten.
