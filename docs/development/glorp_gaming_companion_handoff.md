# Pre-GLORP gaming companion handoff

**Source baseline:** `196e049c4f1f204e9be4fb71a29b5033c86417fe`  
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
  adds a short-reply instruction to the exact admitted prompt.
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

- **Split WSL2/Windows bridge:** the current forwarder and demo use unauthenticated
  UDP and default to loopback. They are suitable only for the current same-host
  local demo. Do not change the destination to a WSL/Windows interface address
  or expose the listener to the LAN. A versioned authenticated bridge, source
  and generation binding, replay protection, reconnect/backpressure behavior,
  and Windows-side observer adapter do not exist yet. The new envelope library
  is not connected to either receiver. Its tests use an in-memory stream adapter
  because this sandbox denies socket-pair writes; no real socket or
  Windows/WSL interoperability is claimed. Source-key custody and generation
  rotation on process restart are not implemented. The sequence high-water mark
  is process-local, so callers must rotate to a fresh generation before
  restarting a receiver or old messages may be accepted again within the
  timestamp window.
- **Topology and lifecycle:** no companion deployment manifest or one-command
  readiness doctor currently composes WSL core, Windows observer, renderer, and
  local speech. The existing Windows readiness and scheduled-task machinery is
  for maintenance, not companion startup. There is no coordinated start,
  health check, reconnect, or shutdown for a split deployment.
- **Resource feedback:** the governor in `host_resource_governor.py` emits
  proposal-only reports. It does not control inference. Gaming mode shortens
  direct chat requests but does not reduce llama.cpp thread counts, unload the
  model, pause optional background inference, reserve GPU capacity, or ensure
  better game frame times. No GLORP CPU/GPU/VRAM, temperature, power, or frame
  time measurements are present.
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
- **Perception and situated behavior:** there is no connected, opt-in Windows
  screen-capture-to-cognition path. Foreground process matching identifies an
  allowlisted executable only; it does not see game content. No ambient screen,
  microphone, or provider capture should be enabled.
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

The chat test proves the local software path from fixture-backed conversation
to authorized commanded avatar state, mode update, receiver normalization, and
durable conversation reload. Separately, the headless Godot test proves that
the actual procedural scene applies a wave and smile, reports post-apply state,
and that Python passes this report through the embodiment owner without
upgrading it to effect proof or independent observation. These two test paths
are not yet connected to each other by a running bridge. No independent
physical consequence is proved.

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

1. Add a deployment manifest and read-only doctor for the split topology, with
   explicit `blocked`, `ready_with_warnings`, and `ready` facts; it must never
   create installation identity, grants, receipts, firewall rules, or services.
2. Add independently configured source-key custody, generation rotation, a
   bounded listener/client lifecycle, reconnect and backpressure. Keep
   non-loopback transport disabled until that work is validated.
3. Connect the bridge to the real foreground observer and admitted avatar
   output, then compose startup, health, reconnect, and shutdown.
4. Add measurement adapters, then an explicitly authorized request-budget
   effect owner; retain proposal-only host governance until that owner is
   separately admitted.
5. Connect renderer reports through the bridge and durable World-State capture;
   add independently sourced observation, then opt-in perception and speech
   paths.
6. Repeat the same vertical scenario after each connection, labeling fixtures,
   actual CPU inference, and GLORP hardware observations separately.
