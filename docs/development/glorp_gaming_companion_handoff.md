# Pre-GLORP gaming companion handoff

**Source baseline:** `71f5424112e379b21a650d9069305761554a30b9` (verified `main` at the start of this integration increment)
**Host target:** Windows 11 + WSL2, RTX 3060 12 GB, Ryzen 5 5600X, 32 GB RAM  
**Status:** software checkpoint in progress; not a deployable split-host release.

**Campaign continuation update (2026-11-02; worktree parent
`c4b200d930b1505232922f140cad95e14e223dee`):** this cloud increment adds
host-pressure deferral, a Windows performance observer, durable renderer-report
capture, mTLS transport primitives, and an in-process generation-aware bridge
supervisor. This continuation also adds governed speech timing/interruption
events, a loopback renderer-report edge relay, and one-command local fixture
acceptance. Focused local tests pass; hosted Required / Quality Gate has not run
for this increment. The hardware and cross-platform claims below remain open.

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
- The host-resource coordinator now forwards each validated proposal-only
  evaluation to the runtime governor. Background local inference defers when
  fresh telemetry reports CPU, memory, GPU, or thermal pressure, or when
  required CPU/RAM evidence is incomplete. Foreground chat remains eligible;
  a deferred request does not reserve its correlation ID and can be admitted
  after a later low-pressure observation. Receipts carry evaluation, epoch,
  snapshot, and report references. Fixture tests cover the path; no GLORP
  measurement is claimed.
- `WindowsGamePerformanceObserver` parses bounded PresentMon CSV and optional
  selected-process CPU/RSS readings. It reports p50/p95/p99 frame times,
  hitches over 50 ms, source digests, and explicit unsupported/unavailable
  states. CSV reads have a 4 MiB bound; the psutil CPU sample uses a short
  finite measurement interval instead of psutil's documented meaningless first
  nonblocking zero. Offline fixtures cover parsing, bounded input, provider
  digest validation, and Linux unsupported reporting. Signed reports now travel
  through the authenticated bridge; the core verifies expected source,
  generation, freshness, strict shape, and provenance before using the sample
  as supplemental background-inference pressure evidence. A p95 of at least
  50 ms or any >50 ms hitch defers background work while fresh; this signal
  never substitutes for required core CPU/RAM evidence. HMAC and mTLS fixtures
  cover the path; no Windows API or GLORP gameplay measurement is claimed.
- The mTLS runtime now has a bounded in-process `CompanionBridgeSupervisor`.
  Recovery requires independent source and acknowledgment generation records,
  externally verified receipts for both chains, and a runtime whose configured
  identities match that pair. Failure injection covers rotation, binding
  mismatch, exhausted restart budget, close-during-recovery, and detector
  reconnection. This does not issue
  credentials, establish firewall rules, install startup persistence, or
  supervise Windows and WSL as operating-system services.
- `GamingCompanionProcessSupervisor` now manages one explicitly authorized
  foreground edge/core child process. It validates a bounded no-shell command,
  strips inherited credential-bearing environment variables, binds launch
  approval to the exact command digest and generation pair, probes readiness,
  performs graceful shutdown, and restarts only with verified rotated source
  and acknowledgment generations. A real child-process fixture covers startup,
  crash recovery, denied-launch no-spawn behavior, and shutdown. It installs no
  service or login persistence and does not resolve either platform's key store.
- Verified incoming renderer reports can be saved as content-addressed,
  permission-restricted evidence with their exact signed envelope and lineage.
  World-State revalidation preserves the boundary that this is renderer
  self-report, not independent observation or proof of physical effect. Godot
  still has no mTLS sender. A headless Godot integration test now sends its
  report over loopback UDP through the edge relay and mTLS into durable capture.
  The relay cannot independently establish which local process emitted its UDP
  datagram, and no Windows-to-WSL run is claimed.
- Local speech now records active and last-played turn identities, cancels the
  active turn when revoked, and best-effort stops/discards same-conversation
  speech when a new user turn begins. Focused controller and chat-service tests
  cover the interruption path. pyttsx3 word-start events now publish turn-bound
  character offsets and elapsed time through the governed avatar state channel;
  utterance boundaries and interruption are recorded separately. A bounded
  asynchronous event queue keeps avatar-state writes off the audio callback;
  dropped timing events are counted. The system does not infer phonemes or
  fabricate visemes. Godot now opens/closes the procedural mouth from the
  actual utterance/interruption boundary event and reports that rendering as
  self-report; it does not synthesize word-shaped visemes. Windows/WSL speaker
  routing and target timing remain unmeasured. The reverse mTLS command now
  carries the closed word-timing event to the Windows state-file queue; the
  localhost certificate-backed test verifies timing metadata reaches that
  renderer input. Godot can animate generic speech activity from those timing
  events, but does not map word offsets to phonemes or authored visemes.
- `python -m scripts.gaming_companion_acceptance --manifest <deployment.json>
  --results-dir <private-results-directory>` runs the local fixture suite and
  read-only deployment doctor, retaining restricted logs, JUnit summary, and
  digests. Its result marks target-host validation as not run and never claims
  production commissioning.

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

After the WSL checkout, interpreter, and operator-issued records exist, run
the local acceptance/doctor commands from that checkout:

```text
python -m scripts.gaming_companion_deployment_cli validate --manifest <deployment.json>
python -m scripts.gaming_companion_deployment_cli doctor --manifest <deployment.json>
python -m scripts.gaming_companion_acceptance --manifest <deployment.json> --results-dir <new-private-results-directory>
```

The documented local avatar launcher is:

```text
python -m sentientos.cli.avatar_demo_cli \
  --state-file <same-private-avatar-state-path> \
  --godot-bin <installed-godot-executable> \
  --renderer-report-relay-port <operator-configured-loopback-port>
```

Omit `--renderer-report-relay-port` when no edge relay is running. The Godot
sender has no remote host option and only targets `127.0.0.1`; failed or
unavailable report delivery does not retry or change the renderer's output.

Both entrypoints expose `--help`. The avatar launcher starts the forwarder and
Godot child when the supplied executable/project exist; interrupting the
launcher stops its forwarder and terminates the child. A separately verified
chat startup, avatar-session opt-in, and chat shutdown sequence has not yet been
run as one deployment procedure. There is not yet a Windows-edge command that
loads DPAPI and generation custody, starts the observer/renderer relay, and
supervises it as an OS process; no such command is listed as runnable until it
is implemented and tested.

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
  generations; uncertain deliveries are not replayed. Both in-process listener
  supervision and a separately tested local child-process supervisor are
  available, but no paired Windows/WSL role launcher composes them yet. The
  `BridgeChatAvatarOutputEmitter` now creates visual-only commands from an
  admitted chat response; `MutualTLSAvatarCommandSender` signs and transmits
  each command once using the protected edge mTLS client. On Windows,
  `WindowsEdgeAvatarCommandDispatchOwner` requires an external receipt
  verifier before submitting a command to `WindowsGodotAvatarStateQueue`,
  which writes the visual-only state format consumed by the existing Godot
  forwarder. A real certificate-backed localhost mTLS test exercises
  chat-command encode/send/receive/receipt-check/state-file delivery. A real
  Windows listener, authority-log resolver, paired runtime launcher, and
  renderer observation are not yet composed; state-file delivery does not
  establish that a frame rendered.
- **Topology and lifecycle:** the closed deployment manifest and read-only WSL2
  doctor now exist, but the doctor cannot observe Windows components or a live
  bridge from this cloud Linux environment. Bounded local child-process
  supervision is tested, but there is still no coordinated cross-platform
  startup/shutdown, exact Windows-edge/WSL-core role entrypoints, OS service
  registration, custody-reference resolution, firewall setup, or target-host
  recovery validation. The Windows readiness and scheduled-task machinery
  remains specific to maintenance.
- **Resource feedback:** the governor in `host_resource_governor.py` remains
  proposal-only. The exact llama.cpp worker now applies the gaming request's
  two-thread ceiling to decode and batch work, clamped to the commissioned
  profile and restored after each call. This request-local limit does not unload
  the model, preempt an already-running decode, reserve GPU capacity, change
  host scheduling, or ensure better game frame times. New background inference
  admissions now defer until a fresh host observation is available and defer
  again under reported pressure. No GLORP CPU/GPU/VRAM,
  temperature, power, or frame-time measurements are present.
- `sentientos.gaming_companion_deployment` and its CLI provide a closed split-host
  manifest and read-only WSL2 deployment doctor. The doctor reports absent
  Windows and bridge evidence; it does not create state, grant authority, start
  components, or claim that the deployment is ready.
- **GPU telemetry:** the NVML collector has fixture coverage only in this cloud
  run. NVML is not installed here, and no GLORP device sample exists.
  Per-process GPU utilization remains unimplemented. Game frame-time collection
  has an offline-tested Windows adapter, authenticated bridge publisher/core
  detector, and supplemental pressure-policy input. Real Windows counters,
  PresentMon capture, and gameplay effects remain unmeasured on GLORP.
- **Renderer feedback:** Godot now produces a bounded in-memory
  `sentientos.avatar_renderer_report:v2` after applying a state. Ingress
  continues to accept archived v1 reports and validates the v2 speech activity
  subrecord without accepting phoneme claims. It includes
  session/turn/output lineage when available, the commanded state, post-apply
  animation and transform values, expression result, FPS cap, timing, and a
  source digest. A Python ingress validates its closed shape and projects it
  through the existing embodiment evidence owner as an explicitly unverified
  renderer self-report. An actual headless Godot scene probe exercises this
  path. The Python ingress can durably capture reports through an optional
  loopback-only Windows edge relay that signs the unchanged report and sends it
  over mTLS. The headless Godot→relay→mTLS→store fixture passes. This remains
  renderer self-report: the source digest is a renderer claim, and loopback UDP
  does not authenticate the Godot process. The
  procedural demo is not the inspected Blender-authored candidate and is not an
  adopted body.
- **Perception and situated behavior:** the bounded, opt-in Windows game capture
  and local OCR owner now has an authenticated loopback bridge into the chat
  screen-observer interface. The vertical scenario runs fixture capture/OCR
  through a real loopback socket before persistent chat and Godot rendering.
  This is same-host software integration, not Windows-to-WSL transport, a live
  desktop capture, or actual game perception by a local model. No ambient
  screen, microphone, or provider capture should be enabled.
- **Speech:** production chat has a separately admitted local TTS path and
  software-level interruption handling. Word timing now crosses the tested
  localhost mTLS reverse route to the Godot state input, where the procedural
  mouth animates from utterance and interruption boundaries. Actual playback,
  Windows/WSL routing, and target timing remain untested. The unadopted authored
  candidate probe now applies a separately mapped generic speech-activity
  blend shape and verifies interruption closes it; word-start offsets are not
  treated as phonemes or visemes, and this is not evidence of an adopted body.
- **Authored-body adoption:** authoring, structural inspection, operator
  adoption, compare-and-swap lineage, rollback, and an experimental Godot
  candidate adapter exist. The demo's active body remains procedural; it has
  not loaded the adopted GLORP artifact with its production manifest and
  renderer handoff. Target prerequisites include an operator-adopted artifact,
  its current pointer/manifest/receipt chain, the required Blender/Godot import
  support, and a target renderer process that can load the exact asset digest.
- **Local model:** the rootless smoke proves that one small CPU model can run in
  this cloud environment under the experimental owner. It does not establish a
  commissioned GLORP model, the suitability of Hermes 4 14B, CUDA availability,
  game responsiveness, or production installation authority.

## Code-level scenario result

The focused test node
`tests/test_chat_service_hardened_serving.py::test_gaming_companion_vertical_fixture_survives_forwarding_and_restart`
passed with the related avatar receiver, foreground detection, and serving
budget tests, the new bridge protocol tests, and NVML collector tests. Its
inference implementation is
a deterministic fixture. The independently preserved rootless model smoke is
real inference, but it was not substituted into this test because it is not the
production serving owner and would cross experimental custody boundaries.

The one-command local acceptance workflow most recently passed 182 tests with
zero failures/errors and 23 repository-marked skips. It includes a real
Blender-authored GLB candidate exercised in headless Godot because both tools
were available, plus mTLS Windows-performance transport fixtures and the
vertical chat/avatar restart scenario. The Blender/Godot body remains a
non-adopted candidate. The local deployment doctor correctly reported WSL2,
host configuration, and target checks as unobserved; this was software
validation, not production commissioning.

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
telemetry. The loopback bridge authenticates but does not encrypt. Cross-host
deployment uses the separate TLS 1.2+ mTLS transport, which has local
certificate-fixture coverage but no Windows/WSL reachability result.

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

## Remaining software engineering increments

The cloud checkpoint has completed bounded background-inference deferral and
recovery from validated host CPU/RAM/GPU/thermal evidence, with receipt-linked
resource measurements. It also adds protected mTLS transport primitives,
source-key readers, verified generation rotation, in-process listener and
authority-gated child-process supervisors, a fixture-tested Windows
performance adapter with pressure-policy input, durable renderer self-report
capture, and turn-scoped speech interruption. These are component increments,
not a complete Windows-edge/WSL-core deployment.

1. Implement the exact Windows-edge and WSL-core entrypoints that resolve the
manifest's protected references, construct the observed core and edge
components, and supply authority-backed launch and health callbacks to the new
process supervisor. Do not create keys, generations, certificates, firewall
rules, or OS persistence.
2. Compose the existing reverse-route producer and dispatcher with a real
Windows mTLS listener, an authority-backed receipt resolver, and a bounded
Godot command queue. Run failure injection for queue rejection, transport
uncertainty, restart, and generation rotation without replaying uncertain
messages.
3. Execute the Godot report return route on Windows/WSL through the loopback
edge relay, protected mTLS bridge, and durable World-State capture. The
software-only relay integration test passes; target transport and attribution
remain unverified. Keep authenticated relay identity separate from renderer
self-report and independent physical observation.
4. Use `load_adopted_body` to resolve the current adopted artifact only after
an authority-backed receipt verifier, manifest binding, content hash, and
allowed artifact root all agree. Wire its descriptor to Godot import/rollback
and preserve the adoption lineage. The loader is implemented and fixture
tested; no operator-adopted GLORP artifact has been loaded.
5. Connect existing timing events to an explicitly adopted body's authored
   mouth rig using its explicit generic speech-activity mapping while keeping
   word offsets distinct from phoneme labels. The unadopted candidate now has
   a fixture-tested path. Verify actual local audio latency and immediate
   renderer interruption on target after adoption.
6. Extend the local acceptance command into the supervised cross-platform
commissioning workflow after protected Windows/WSL custody and OS service
interfaces are available. Current local command invokes the existing software
owners, includes failure-injection fixtures, and records its outputs, but does
not create target services or authority.
7. Run preregistered GLORP comparisons only after target prerequisites below
are satisfied; report fixtures, rootless CPU inference, and GLORP observations
as separate evidence classes.

## Target-host-only acceptance and prerequisites

These checks are deferred for lack of GLORP access, not treated as a blocker for
the software campaign:

1. Windows API foreground PID/basename consistency and PresentMon process
   attribution. Requires Windows 11, an explicitly allowlisted running game,
   PresentMon, and a controlled foreground/non-game transition scenario.
2. Windows per-process CPU/RSS sampling and optional GPU attribution. Requires
   the selected process, Windows resource APIs or psutil, and a supported GPU
   telemetry provider; absent fields must remain unavailable.
3. WSL2-to-Windows protected bridge route and firewall validation. Requires the
   provisioned WSL distribution, chosen private address mode, operator-approved
   firewall rule, CA/certificates, pinned peer identity, source key in each
   custodian, and externally issued source/acknowledgment generation receipts.
4. Supervised startup, shutdown, reconnection, and generation rotation across
   both processes. Requires authorized credential/generation factories, the
   real WSL core and Windows edge launchers, injected process/service failures,
   and confirmation that uncertain messages are not replayed.
5. Renderer report return and artifact loading. Requires the adopted body
   artifact, current pointer/manifest/adoption chain, configured Godot import
   support, the Windows renderer/relay, and a report-to-WSL transport run.
6. Audio playback and synchronization. Requires a local output device and
   actual backend, measured start/word/finish timing, cancellation while playing,
   and a renderer that consumes those timing events for visemes.
7. Gaming acceptance. Requires preregistered game-only, unrestricted inference,
   and governed-inference sessions with frame-time p50/p95/p99, hitches,
   inference latency/tokens per second, CPU/RAM/GPU/VRAM, temperature, and
   power readings where the providers support them. No improvement threshold
   has been established.
