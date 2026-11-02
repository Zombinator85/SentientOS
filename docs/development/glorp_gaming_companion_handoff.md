# Pre-GLORP gaming companion handoff

**Source baseline:** `71f5424112e379b21a650d9069305761554a30b9` (verified `main` at the start of this integration increment)
**Host target:** Windows 11 + WSL2, RTX 3060 12 GB, Ryzen 5 5600X, 32 GB RAM  
**Status:** software checkpoint in progress; not a deployable split-host release.

This note records what the current source and tests establish. The hardware and
cross-platform claims remain open until the WSL2/Windows system is exercised on
the target host.

## Implemented and executed

- Production chat composes persistent conversation custody, local-model serving,
  invocation admission, and the process-generation handoff. Its launch entrypoint
  is `sentientos-chat`, defined by `pyproject.toml`; it requires installation,
  serving-operation, runtime-handoff, and expected software-generation identities.
- Chat supports `normal`, `gaming`, and allowlisted `automatic` workload modes.
  Automatic mode uses the Windows foreground executable API and degrades to the
  bounded gaming profile when that observation is unavailable. Gaming mode
  constrains each direct chat invocation's input/output/token/time budgets and
  adds a short-reply instruction to the exact admitted prompt. On the exact
  llama.cpp runtime, gaming calls also lower decode and batch CPU threads to at
  most two, clamped to the commissioned profile and restored after the turn.
- An explicitly enabled, per-conversation visual avatar grant publishes the
  exact response through `AVATAR_EMISSION` admission. The state file records
  response digest, turn/session identity, and the current workload mode.
- The Python avatar forwarder reads a bounded state file and sends changed state
  over UDP to the Godot demo. Godot responds to the closed `normal`/`gaming`
  hint by limiting its own frame rate to 60/15 FPS.
- The added fixture-backed vertical test exercises persistent chat, explicit
  avatar admission, the actual Python receiver's state normalization, a live
  mode update without another turn, and conversation recovery after service
  restart. It is not a cross-platform or Godot-process test.
- `sentientos.gaming_companion_bridge` now provides a versioned, size-bounded,
  HMAC-authenticated message envelope, source/session/generation identity,
  timestamp and sequence checks, and length-prefixed stream framing. Avatar
  commands must carry an admission receipt reference. The receiver validates
  transport evidence only; it does not open a listener, persist key material,
  mint authority, or execute a command.
- `collect_nvidia_gpu_observation` adds an optional read-only NVML adapter for
  device-wide GPU utilization, VRAM, temperature, power, and collector overhead.
  It is not in the default collector set; missing dependency/API fields remain
  unavailable and it does not attribute utilization to the model process.
- Actual CPU inference through SentientOS's rootless experimental owner succeeded
  on 2026-11-02 with the already verified Qwen2.5-0.5B-Instruct Q4_K_M artifact
  and `llama-cpp-python 0.3.35`. The exact prompt, response, model/runtime
  identity, timing, resource data, and receipts are preserved in
  `docs/development/evidence/pre_glorp_model_baseline_2026-11-02/`.
  That run is rootless experimental evidence, not production commissioning or a
  gaming-performance trial.

## Exact verified entrypoints

The current production chat CLI arguments were inspected through its declared
entrypoint. A production command must supply actual values from the current
installation, serving, and process-generation records; those values must not be
invented or copied from another installation:

```text
sentientos-chat --installation-identity <issued-identity> \
  --serving-operation-id <admitted-serving-operation> \
  --runtime-handoff-id <issued-runtime-handoff> \
  --expected-software-generation-digest <verified-generation-digest> \
  --host 127.0.0.1 --port 5000 \
  --avatar-state-path <private-local-avatar-state-path>
```

`--avatar-state-path` is optional and opts into the visual output surface; it
does not itself enable the per-session grant. `--local-speech-output` is a
separate opt-in and is omitted above. The supervised process holds an
installation-scoped lock and exits if the supplied records do not verify.

The documented local avatar launcher is:

```text
python -m sentientos.cli.avatar_demo_cli \
  --state-file <same-private-avatar-state-path> \
  --godot-bin <installed-godot-executable>
```

Both entrypoints expose `--help`. The avatar launcher starts the forwarder and
Godot child when the supplied executable/project exist; interrupting the
launcher stops its forwarder and terminates the child. A separately verified
chat startup, avatar-session opt-in, and chat shutdown sequence has not yet been
run as one deployment procedure.

## What remains unfinished

- **Split WSL2/Windows bridge:** the existing avatar forwarder and Godot demo
  still use unauthenticated same-host UDP; Godot binds to `127.0.0.1`. Separately,
  `sentientos.gaming_companion_bridge_runtime` supplies a versioned,
  authenticated, loopback-only TCP listener/client, and
  `sentientos.foreground_game_bridge` supplies a Windows publisher and automatic
  chat detector. Focused tests exercise authenticated localhost delivery and
  detector-to-inference lineage. The production chat composition can own that
  detector, but no coordinated split-host deployment has established
  Windows-to-WSL reachability. Source-key custody, durable generation rotation,
  and startup generation issuance remain external. Queue state and sequence
  high-water marks are process-local, so every restart needs newly issued source
  generations; uncertain deliveries are not replayed.
- **Topology and lifecycle:** the closed deployment manifest and read-only WSL2
  doctor now exist, but the doctor cannot observe Windows components or a live
  bridge from this cloud Linux environment. It does not supervise or start
  processes. There is still no coordinated startup, health check, reconnect, or
  shutdown for a split deployment. The Windows readiness and scheduled-task
  machinery remains specific to maintenance.
- **Resource feedback:** the governor in `host_resource_governor.py` remains
  proposal-only. The exact llama.cpp worker now applies the gaming request's
  two-thread ceiling to decode and batch work, clamped to the commissioned
  profile and restored after each call. This request-local limit does not unload
  the model, pause optional background inference, reserve GPU capacity, change
  host scheduling, or ensure better game frame times. No GLORP CPU/GPU/VRAM,
  temperature, power, or frame-time measurements are present.
- `sentientos.gaming_companion_deployment` and its CLI provide a closed split-host
  manifest and read-only WSL2 deployment doctor. The doctor reports absent
  Windows and bridge evidence; it does not create state, grant authority, start
  components, or claim that the deployment is ready.
- **GPU telemetry:** the NVML collector has fixture coverage only in this cloud
  run. NVML is not installed here, and no GLORP device sample exists.
  Per-process GPU utilization and game frame-time collection remain
  unimplemented.
- **Renderer feedback:** Godot now produces a bounded in-memory
  `sentientos.avatar_renderer_report:v1` after applying a state. It includes
  session/turn/output lineage when available, the commanded state, post-apply
  animation and transform values, expression result, FPS cap, timing, and a
  source digest. A Python ingress validates its closed shape and projects it
  through the existing embodiment evidence owner as an explicitly unverified
  renderer self-report. An actual headless Godot scene probe exercises this
  path. The report is not yet transported to chat, durably captured, or an
  independent observation; its source digest is still a renderer claim. The
  procedural demo is not the inspected Blender-authored candidate and is not an
  adopted body.
- **Perception and situated behavior:** the bounded, opt-in Windows game capture
  and local OCR owner now has an authenticated loopback bridge into the chat
  screen-observer interface. The vertical scenario runs fixture capture/OCR
  through a real loopback socket before persistent chat and Godot rendering.
  This is same-host software integration, not Windows-to-WSL transport, a live
  desktop capture, or actual game perception by a local model. No ambient
  screen, microphone, or provider capture should be enabled.
- **Speech:** production chat has a separately admitted local TTS path, but
  actual playback, Windows/WSL routing, interruption, and timing-aligned
  visemes have not been exercised on the target host.
- **Local model:** the rootless smoke proves that one small CPU model can run in
  this cloud environment under the experimental owner. It does not establish a
  commissioned GLORP model, the suitability of Hermes 4 14B, CUDA availability,
  game responsiveness, or production installation authority.

## Code-level scenario result

The focused test node
`tests/test_chat_service_hardened_serving.py::test_gaming_companion_vertical_fixture_survives_forwarding_and_restart`
passed with the related avatar receiver, foreground detection, and serving
budget tests, the new bridge protocol tests, and NVML collector tests (68 tests in the latest focused
run). Its inference implementation is
a deterministic fixture. The independently preserved rootless model smoke is
real inference, but it was not substituted into this test because it is not the
production serving owner and would cross experimental custody boundaries.

The test node
`tests/test_gaming_companion_vertical_godot.py::test_fixture_screen_observation_reaches_real_godot_without_persisting_screen_data`
uses the consent-checked Windows capture and OCR owners with fixture frame/OCR
providers, transmits their bounded result over the authenticated loopback bridge,
and supplies the verified observation to persistent chat. It then exercises
per-session `AVATAR_EMISSION`, the avatar state file, the actual headless Godot
scene, renderer report lineage, and chat transcript recovery after restart. The
fixture OCR text is present in the inference prompt but not the persisted
transcript or avatar state. Godot's renderer report remains an unverified
self-report, and no independent physical consequence is proved. The separate
headless probe checks an authored wave clip and expression behavior.

This scenario does not establish real Windows capture, Windows-to-WSL
connectivity, production model execution, game performance, or hardware
telemetry. HMAC authenticates the loopback message but does not encrypt it; the
bridge must not be moved off loopback for cross-host use without a separately
designed protected transport.

## GLORP acceptance sequence

Do not start until the target Windows/WSL host has been explicitly provisioned
and the current installation/runtime/model/serving/process-generation receipts
exist. No such target-host authority or receipts are available in this cloud
workspace. The following is the exact current sequence that the source supports;
the unresolved split-network step prevents calling it a complete deployment:

1. In the provisioned WSL repository environment, use the actual verified
   values from the active installation and process-generation records with the
   `sentientos-chat` command above. Keep the server on `127.0.0.1` until the
   authenticated cross-environment bridge is implemented.
2. In a compatible local desktop session, run the avatar-demo launcher above
   with the same private state path. Its current default UDP route is loopback;
   do not change it to a LAN or WSL interface address.
3. Create a chat session and explicitly enable visual avatar output for that
   session. Test normal/gaming transitions, revoke the grant, and terminate both
   processes. Restart chat and verify conversation recovery and that the
   ephemeral avatar grant did not survive.
4. Before using the Windows foreground observer from WSL, add and test the
   authenticated bridge and lifecycle components listed above. Without that
   bridge, automatic foreground mode on Linux reports the detector as
   unsupported and selects the conservative gaming budget.
5. Only after the software topology works, conduct the preregistered GLORP
   game-only, unregulated-inference, and governed-inference comparisons. Record
   frame-time p50/p95/p99, hitches, tokens/sec, inference latency, CPU/RAM/GPU/
   VRAM, temperature, and power where available. No pass threshold or expected
   performance improvement has been established.

## Next engineering increments

1. Establish independently configured source-key custody and restart generation
   rotation, then coordinate the existing bounded listener/client lifecycle
   across Windows and WSL. Validate target-host routing without changing the
   loopback-only listener or exposing it to a LAN.
2. Compose the existing Windows foreground publisher, authenticated bridge, and
   production chat detector under an authorized split-host launcher. Verify
   stale, invalid, or missing observations retain the conservative gaming
   budget.
3. Connect renderer reports through the bridge and durable World-State capture;
   preserve their self-reported status until an independent observer exists.
4. Compose startup, health, reconnect, and shutdown around the read-only
   deployment doctor without creating installation identity or grants.
5. Extend the governed request-budget policy using measured CPU/GPU/VRAM and
   game frame-time inputs, preserving the current request-local llama.cpp thread
   ceiling. HostResourceGovernor remains proposal-only; no game frame-time
   improvement has been measured.
6. Run preregistered GLORP comparisons only after the target host is provisioned;
   report fixtures, rootless CPU inference, and GLORP observations separately.
