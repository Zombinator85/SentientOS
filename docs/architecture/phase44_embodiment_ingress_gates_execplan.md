# Phase 44 ExecPlan: Embodiment ingress gates

1. **Current Phase-43 fusion state**
   - `sentientos.embodiment_fusion` produces deterministic non-authoritative snapshots with modality/risk/provenance fields.
2. **Mutation/action sinks inspected**
   - `mic_bridge.py` memory append path.
   - `feedback.py` feedback side-effect action path.
   - `vision_tracker.py`, `multimodal_tracker.py`, `screen_awareness.py` direct JSONL logs + sensitive telemetry.
   - `task_admission.py`, `task_executor.py`, `sentientos/control_api.py`, `sentientos/ledger_api.py`, `sentientos/orchestration_intent_fabric.py`, `sentientos/embodiment/consent.py`, `sentientos/introspection/spine.py` checked for boundary relationship (no direct ingress coupling).
3. **Target gate shape**
   - New canonical `sentientos.embodiment_ingress` module.
   - Input: Phase-42/43 compatible telemetry/snapshots.
   - Output: non-authoritative ingress receipt with recommendation posture and optional candidates.
4. **Memory/action pressure classes**
   - memory write pressure (audio/stt)
   - feedback action pressure
   - biometric/emotion pressure
   - multimodal summary pressure
   - screen/OCR privacy pressure
   - incomplete context pressure
5. **Consent/privacy/retention considerations**
   - privacy/biometric pathways return hold postures.
   - raw retention and consent-required signals degrade to hold.
   - no mutation authority delegated.
6. **Relationship to admission/control/orchestration APIs**
   - ingress is proposal-only; does not import admission/execution/control internals.
   - downstream systems may consume receipts later via approved facades.
7. **Tests to add/update**
   - new focused ingress tests for posture classification, determinism, provenance.
   - architecture boundary assertions + manifest declaration.
8. **Unresolved risks and deferred work**
   - legacy modules still write memory/actions/logs; this phase only adds canonical ingress visibility.
   - full runtime replacement and enforcement remains deferred to later phases.
