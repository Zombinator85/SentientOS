# Phase 40 Boundary Remediation ExecPlan

## 1) Remaining known violations from manifest
- `autonomous_self_patching_agent.py` expressive forbidden import.
- `self_patcher.py` expressive forbidden import.
- `speech_emitter.py` expressive forbidden import.
- `tts_test.py` expressive forbidden import.

## 2) Additional discovered violations (same classes)
- Additional expressive coupling in legacy speech/self-patch tooling via `control_plane`/`task_executor` direct imports.
- Governance-annotation policy currently relies on a broad `approved_paths` allowlist; many approved files still lacked parseable governance markers.

## 3) Selected remediation batch
- Migrate speech/self-patch callers (`speech_emitter.py`, `self_patcher.py`, `tts_test.py`) to public control façade APIs.
- Remove remaining expressive direct formal import in `autonomous_self_patching_agent.py`.
- Add governance annotation constants to selected daemon/agent/scheduler modules:
  - `daemon_autonomy_supervisor.py`
  - `avatar_autonomous_ritual_scheduler.py`
  - `sentientos/forge_daemon.py`
  - `agent_privilege_policy_engine.py`
- Tighten architecture boundary tests so approved autonomy files must still carry parseable governance markers.
- Update manifest truth and promote stricter autonomy annotation enforcement posture.

## 4) Why this batch is safe together
- All touched callers are boundary adapters/CLIs and can delegate to existing canonical control semantics through `sentientos.control_api` without changing authority behavior.
- Governance annotation additions are metadata-only and do not change runtime.
- Test + manifest changes align machine enforcement with repository truth.

## 5) Target façades/helpers/annotations
- Extend `sentientos.control_api` with narrow delegation helpers for speech authorization/admission and self-patch provenance serialization.
- Use consistent markers: `GOVERNANCE_ANNOTATION`, `ADMISSION_SURFACE`, `CONSENT_BOUNDARY`, `PROVENANCE_BOUNDARY`, `SIMULATION_ONLY`, `NON_SOVEREIGNTY`, `CALLER_TRIGGERED_OR_BOUNDED_RUNTIME`.

## 6) Exact files expected to change
- `docs/architecture/phase40_boundary_remediation_execplan.md`
- `sentientos/control_api.py`
- `speech_emitter.py`
- `self_patcher.py`
- `tts_test.py`
- `autonomous_self_patching_agent.py`
- `daemon_autonomy_supervisor.py`
- `avatar_autonomous_ritual_scheduler.py`
- `sentientos/forge_daemon.py`
- `agent_privilege_policy_engine.py`
- `sentientos/system_closure/architecture_boundary_manifest.json`
- `tests/architecture/test_architecture_boundaries.py`

## 7) Validation and compatibility strategy
- Run architecture + import purity tests.
- Run orchestration smoke tests requested for boundary safety.
- Preserve all existing record shapes/paths and admission semantics by delegating instead of re-implementing policy.

## 8) Deferred violations
- Broad protected-sink write normalization across many expressive/world scripts remains deferred due to scope/compatibility risk; this wave focuses on control-boundary coupling and governance enforcement hardening while keeping manifest truthful.
