# Governed local inference under host pressure

The host-resource observation runtime can forward a validated, proposal-only
evaluation to the runtime governor. This input contains the observation epoch,
snapshot and pressure-report identifiers, pressure labels, CPU/RAM values,
device-wide GPU/VRAM values when available, and observation time. It does not
grant host mutation or inference authority. For multiple NVIDIA devices the
highest valid utilization sample is retained so a loaded device is not hidden
by averaging it with idle devices. NVML samples are device-wide and do not
identify which process or model caused the load.

In enforced mode, background local-model inference is deferred when no fresh
host evaluation exists, required CPU/RAM values are incomplete, the evaluation
reports CPU, memory, GPU, or thermal pressure, or the runtime governor reports
its own warning-level pressure. Host evidence is considered current for 120
seconds. A deferred admission does not reserve the correlation ID, enter the
model backend, or debit a resource allocation. A later request with the same
correlation ID can proceed after a fresh low-pressure observation.

Requests whose purpose is `local_user_chat` use the foreground path. This
policy does not defer them on host-evidence absence or host pressure; their
separate inference budgets and admission checks still apply.

An admitted effect is recorded by the governed local-model invoker. When a
resource allocation is supplied, its measured completion receipt is linked to
the exact invocation receipt digest and reconciled in the resource ledger.
Observation evidence and execution receipts are separate records. Fixture
tests cover deferral, no backend entry while deferred, recovery after a fresh
observation, and receipt linkage. They do not claim that this cloud or GLORP
hardware was measured.

The Windows game frame-time adapter forwards authenticated frame-time and
process-resource observations to the governor with their own source,
generation, sequence, message, and digest provenance. Fresh frame-time
pressure defers background inference, and a fresh
low-pressure observation permits a later attempt. A missing or stale game
observation remains unavailable; frame-time is never inferred from CPU/RAM or
GPU pressure.

GPU/VRAM pressure reaches the same background admission check through NVML when
that collector is available. The samples remain device-wide. Per-process GPU
attribution and runtime-specific GPU-offload requirements are not established
by this telemetry, and absent NVML data must not be interpreted as an idle
device or as proof that a model used no accelerator.
