# 0101 — Observe the supervised interpreter image without claiming loaded-code identity

Source baseline: `b8d87a1bea423ca5d5cb103c5002100fe04cf8b3`, tree `6fe42a64e32104a36aa1b99149652cf682998c6c`.

The prior checkpoint identified no independent observation of what executable image the separately supervised chat process was running. Added a bounded Linux procfs observation at the existing runtime owner: it binds PID, parent PID, kernel process-start ticks, expected and observed executable paths, and the SHA-256/size of the opened executable image. It checks process identity and executable inode/path stability around the bounded read. Unsupported platforms, inaccessible procfs, and unstable observations remain explicitly unavailable. The record grants no authority.

Runtime observation schema v4 carries the nested process observation; the reader preserves v1-v3 compatibility and verifies exact nested fields and digest. Its short publication coalescing now notices stable interpreter identity changes immediately. The existing World-State projector validates the v4 projection and retains it in historical evidence; bounded developmental writeback and longitudinal self-model projections preserve the interpreter observation identities. All layers continue to label loaded Python modules `not_independently_attested` and historical runtime currentness unknown after observation time.

The real live-child fixture now exercises the launcher handoff, procfs observation, durable read, World-State projection, and a contradictory parent-match mutation with recomputed nested and outer digests. The independent consumer rejects the contradiction. No model inference is involved.

A focused run first exposed an existing local-name shadowing defect in `resource_consumption_world_state_records`: loop variables named `digest` made the imported canonical digest function unavailable at the runtime-observation projection call. Renamed those locals so the existing real projector path works. The final focused set passed: 76 collected, 75 passed, 1 pre-existing legacy-policy skip. Initial test attempts without temporary governance roots failed while trying to initialize `/glow` on a read-only filesystem; the successful rerun supplied isolated temporary roots.

Commands:

- `python -m py_compile sentientos/chat_process_generation.py sentientos/host_resource_runtime.py sentientos/resident_developmental_writeback.py sentientos/longitudinal_self_model.py tests/test_local_model_chat_runtime_startup.py tests/test_longitudinal_self_model.py`
- `SENTIENTOS_GOVERNOR_ROOT=/tmp/sentientos-v5-run-governor SENTIENTOS_FEDERATION_ROOT=/tmp/sentientos-v5-run-federation SENTIENTOS_CONTROL_KERNEL_ROOT=/tmp/sentientos-v5-run-kernel SENTIENTOS_RUNTIME_STATE_ROOT=/tmp/sentientos-v5-run-runtime SENTIENTOS_REPO_ROOT=/workspace/work/sentientos-a54-exact .venv/bin/python -m pytest -q tests/test_local_model_chat_runtime_startup.py tests/test_resource_invocation_process_generation_integration.py tests/test_host_resource_runtime.py tests/test_longitudinal_self_model.py tests/test_resident_developmental_writeback.py`

No actual local model, provider, production runtime, or external effect was activated. These tests establish fixture behavior only. The interpreter binary observation does not establish which Python modules were loaded in memory, nor independently attest the measurement issuer. A separately authorized process-instance-bound loaded-image observer remains the exact missing dependency for that stronger claim.
