# Phase 46 ExecPlan: Ingress-Gated Legacy Perception Retention Remediation Wave

## 1) Current Phase 45 gate state
- `mic_bridge.py` already enforces explicit ingress gate modes for direct memory side effects (`proposal_only` vs `compatibility_legacy`).
- `feedback.py` already enforces explicit ingress gate modes for direct action callbacks.
- `sentientos.embodiment_ingress` is non-authoritative and emits receipts/candidates; it currently includes memory/action helpers but no dedicated retention helper family for legacy perception direct writes.

## 2) Direct retention/write paths inspected
Inspected legacy modules and exact write paths:
- `screen_awareness.py`
  - `_log_snapshot`: direct append to `self.log_path` (`screen_awareness.jsonl`) after OCR normalization/telemetry.
- `vision_tracker.py`
  - `FaceEmotionTracker.log_result`: direct append to `self.log_path` (`vision.jsonl`) for face/emotion payload.
- `multimodal_tracker.py`
  - `_log`: direct append to per-person `{person_id}.jsonl` payloads.
  - `_log_environment`: direct append to `environment.jsonl`.

## 3) Selected retention-gating strategy
- Add explicit retention gate markers and default mode constants to all three modules:
  - `EMBODIMENT_RETENTION_GATE_PRESENT = True`
  - `EMBODIMENT_RETENTION_GATE_DEFAULT_MODE = "compatibility_legacy"`
  - `EMBODIMENT_RETENTION_GATE_PROPOSAL_ONLY_SUPPORTED = True`
  - `LEGACY_DIRECT_RETENTION_REQUIRES_EXPLICIT_MODE = True`
- Build ingress receipts via `evaluate_embodiment_ingress(build_embodiment_snapshot([event]))`.
- Add retention-specific ingress helpers in `sentientos.embodiment_ingress` to classify permission and mark fallback preservation state.
- Thread `ingress_gate_mode` into legacy retention write functions.

## 4) Compatibility fallback strategy
- Preserve runtime behavior by default (`compatibility_legacy`) for all three modules.
- In compatibility mode:
  - Keep current direct file appends unchanged.
  - Return/record ingress receipt marked with legacy direct retention preserved state.
- In proposal-only mode:
  - Build receipt/candidate and block direct retention writes.
  - Keep telemetry emission and ingress receipt generation active.

## 5) Privacy/retention posture
- Keep privacy-sensitive posture explicit in receipts:
  - Screen/OCR paths include `privacy_sensitive_hold` context.
  - Vision paths include biometric/emotion-sensitive hold posture.
  - Multimodal paths include fusion/direct-write sensitivity and source modality refs.
- Explicitly mark compatibility mode as unresolved direct retention risk in manifest details.

## 6) Tests to add/update
- Add `tests/test_phase46_ingress_gated_retention.py` with focused, hardware-free tests:
  - Screen proposal-only blocks write, returns receipt.
  - Screen compatibility preserves write and marks legacy preserved.
  - Vision proposal-only blocks write and posture is biometric/privacy hold.
  - Vision compatibility preserves write and marks legacy preserved.
  - Multimodal proposal-only blocks per-person and environment writes with receipt posture visibility.
  - Multimodal compatibility preserves writes and marks legacy preserved.
  - New ingress retention helpers remain non-authoritative and perform no writes.
- Update architecture boundary tests for new gate markers and manifest visibility expectations.

## 7) Deferred risks and why
- Direct write paths remain in compatibility mode by design to preserve behavior; full migration to canonical sinks is intentionally deferred.
- This phase does not alter telemetry bridge publication or canonical perception adapters.
- This phase does not add authority, admission, or execution semantics to ingress.
