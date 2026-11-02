# Gaming companion deployment contract

`sentientos.gaming_companion_deployment:v1` describes the intended split
deployment: the persistent SentientOS core and POSIX conversation custody live
on the WSL2 Linux filesystem; Windows supplies foreground-game observation,
Godot rendering, and local audio output. It is a configuration contract and
readiness report. It does not install WSL, create an installation identity,
start a service, add a firewall rule, capture a screen, enable speech, or issue
an authority receipt.

## Validate and inspect

Install the project in the target WSL environment, then run:

```text
sentientos-gaming-companion-doctor validate --manifest <deployment.json>
sentientos-gaming-companion-doctor doctor --manifest <deployment.json>
```

The same commands work through the module entrypoint:

```text
python -m scripts.gaming_companion_deployment_cli validate --manifest <deployment.json>
python -m scripts.gaming_companion_deployment_cli doctor --manifest <deployment.json>
```

`validate` checks a closed schema and opt-in defaults. `doctor` performs
read-only local checks for WSL2, repository and interpreter paths, an existing
Linux-native state directory outside the source checkout, and the installed
chat entrypoint. It reports bridge runtime source presence separately from a
live bridge listener: source code in the checkout does not prove a configured
or running listener. It explicitly reports that Windows components and a live
authenticated bridge were not observed from the WSL process. The doctor never
creates missing paths. Its output is readiness evidence, not installation,
runtime, model, or consent authority.

For one-command local acceptance, run this from the repository checkout after
creating the manifest:

```text
python -m scripts.gaming_companion_acceptance \
  --manifest /path/to/deployment.json \
  --results-dir /path/to/private/acceptance-run
```

The command runs the repository test runner over host-pressure admission,
governed local-model invocation, deployment validation, loopback mTLS,
in-process and child-process supervisor recovery, Windows-observer fixtures, renderer evidence, speech
interruption, and vertical chat/avatar scenarios. When Blender and Godot are
installed, it also runs an actual Blender GLB authoring and headless Godot
candidate-rendering scenario. The report distinguishes that non-adopted
candidate from fixtures and records component availability. The command runs
the read-only doctor and retains a restricted-permission test log, JUnit
summary, and content digest. A passing local suite is reported separately
from the doctor and never claims target-host commissioning. A bounded
foreground process supervisor covers explicitly authorized local launches,
health probing, graceful shutdown, and generation-rotated recovery in a real
child-process fixture. It does not install services or startup persistence,
resolve platform credential stores, or claim that the edge/core roles were
launched here. Windows DPAPI, PresentMon availability, cross-host
firewall/routing, real Windows/WSL role launchers, real audio devices, and an
adopted Blender body remain unrun until target-host acceptance.

`blocked` means a required local precondition is missing. `ready_with_warnings`
means the local checks passed but a configured external component or optional
capability remains unobserved. `ready` requires all required observations.
Neither `ready` status creates permission for chat, avatar, screen capture, or
speech effects. The repository includes a bounded authenticated loopback
listener and client, but this read-only doctor does not start or observe a live
listener. The transport does not provide Windows-to-WSL routing, so this
checkout cannot report a deployable split-host session as ready.

## Manifest example

References identify separately issued records; they are not credential
contents. Leave the identity, serving, and runtime references unset until the
actual installation has issued them. Capture and speech remain manually
activated even when their components are listed.

```json
{
  "schema_version": "sentientos.gaming_companion_deployment:v1",
  "deployment_id": "glorp-gaming-companion",
  "repository_root": "/home/operator/SentientOS",
  "python_executable": "/home/operator/SentientOS/.venv/bin/python",
  "state_root": "/home/operator/.local/share/sentientos",
  "installation_identity_ref": null,
  "serving_operation_ref": null,
  "runtime_handoff_ref": null,
  "software_generation_digest": null,
  "enabled_windows_components": [
    "foreground_observer",
    "godot_renderer",
    "local_audio_output"
  ],
  "bridge_key_reference": null,
  "bridge_bind_scope": "loopback_only",
  "firewall_rule_reference": null,
  "start_on_login": false,
  "automatic_capture": false,
  "automatic_speech": false
}
```

Manifest v1 supports only `loopback_only`. It rejects `private_host_firewall`
and firewall-rule references. Manifest v2 adds a protected mTLS transport, but
an operator-managed firewall rule is still required and cannot be established
from this read-only doctor.

## Mutual-TLS split-host transport (manifest v2)

`sentientos.gaming_companion_deployment:v2` adds the `mutual_tls_private` scope
for a WSL-core/Windows-edge deployment. It requires an exact private bind
address, TLS certificate references, a pinned Windows client-certificate
SHA-256, key and generation-custody references, and an operator-managed
firewall-rule reference. The validator rejects public, wildcard, loopback, and
link-local addresses for this split-host mode. It still treats all references
as declarations: the read-only doctor does not inspect Windows firewall state,
establish connectivity, read key material, or report external components as
ready.

The v2 `bridge_tls` object is closed and uses custody references, not secret
contents. Its form is:

```json
{
  "schema_version": "sentientos.gaming_companion_deployment:v2",
  "deployment_id": "glorp-gaming-companion",
  "repository_root": "/home/operator/SentientOS",
  "python_executable": "/home/operator/SentientOS/.venv/bin/python",
  "state_root": "/home/operator/.local/share/sentientos",
  "installation_identity_ref": null,
  "serving_operation_ref": null,
  "runtime_handoff_ref": null,
  "software_generation_digest": null,
  "enabled_windows_components": ["foreground_observer", "godot_renderer"],
  "bridge_key_reference": "credential-store:sentientos/windows-edge-source",
  "bridge_bind_scope": "mutual_tls_private",
  "firewall_rule_reference": "operator-firewall-rule:sentientos-wsl-core",
  "bridge_tls": {
    "schema_version": "sentientos.companion_bridge_mtls:v1",
    "core_bind_address": "172.20.0.1",
    "port": 54321,
    "server_hostname": "sentientos-wsl-core",
    "ca_bundle_reference": "wsl:/etc/sentientos/bridge/ca.pem",
    "core_certificate_reference": "wsl:/etc/sentientos/bridge/core.pem",
    "core_private_key_reference": "wsl:/etc/sentientos/bridge/core.key",
    "windows_edge_client_certificate_reference": "windows:credential-store/edge-cert",
    "windows_edge_client_private_key_reference": "windows:dpapi/edge-key",
    "expected_windows_edge_certificate_sha256": "<64 lowercase hex characters>",
    "source_key_custody_reference": "credential-store:sentientos/windows-edge-source",
    "source_generation_custody_reference": "operator-ledger:windows-edge-generation",
    "acknowledgment_generation_custody_reference": "operator-ledger:wsl-core-generation"
  },
  "start_on_login": false,
  "automatic_capture": false,
  "automatic_speech": false
}
```

Replace the example references and pin with provisioned values. The certificate
pin is a public certificate digest; private keys and HMAC key bytes stay in
their platform stores.

The executable transport is `sentientos.gaming_companion_tls_transport`. Its
server requires TLS 1.2 or newer, a client certificate trusted by the supplied
CA context, and an exact certificate fingerprint pin. The client requires a
trusted server certificate and hostname validation. The existing HMAC envelope
continues to validate source identity, generation, sequence, freshness, and
message integrity inside TLS. The server binds one literal RFC1918/ULA address;
it never binds `0.0.0.0` or `::`.

The source key remains a separate application secret. On WSL, the
`read_posix_bridge_source_key` reader accepts only a regular file owned by the
current account with no group/world permissions and at least 256 bits. On
Windows, `read_windows_dpapi_bridge_source_key` unseals a DPAPI CurrentUser
protected blob into process memory. These are readers, not key issuers. The
deployment must provision and reference the same source key using the platform
custodians without putting plaintext in the manifest, command line, logs, or
repository.

Source and acknowledgment generations use separate
`sentientos.companion_bridge_generation_custody:v1` records. A restart is valid
only when an external authority receipt verifier accepts both records, each
endpoint identity remains unchanged, both generation and key references rotate,
each successor names its own predecessor, and both issue times advance. The
library does not issue receipts or choose generations. A bridge runtime is one-shot;
after shutdown, a replacement must load newly authorized source and
acknowledgment generations. The Windows foreground publisher opens a fresh
TLS connection for each sample. It does not resend an uncertain delivery; the
next pump interval takes a new sample. `CompanionBridgeSupervisor` can
supervise one in-process runtime, close it, and recover within a fixed restart
budget. Its factory must return a fresh runtime bound to the successor source
and acknowledgment identities. The supervisor checks both receipts and both
predecessor chains and rejects any runtime identity mismatch before starting
it. A failed receipt, factory, or listener start stops
recovery. The supervisor does not mint generations, reload credential stores
itself, configure the firewall, install startup persistence, or manage Windows
and WSL as separate operating-system services. The production foreground
detector can read through the supervisor and follows its active generation
after recovery. The Windows pump remains an explicitly started component.

The local test suite exercises mTLS delivery on loopback with ephemeral test
certificates, peer pinning, HMAC envelope validation, private-key custody
checks, and generation-rotation rules. It does not establish Windows DPAPI
behavior, Windows/WSL routing, firewall state, actual certificate enrollment,
or target-host process supervision. Those remain specific GLORP acceptance
checks; no firewall or credential has been created by the cloud implementation.

## Current deployment limit

The authenticated envelope and replay checks live in
`sentientos.gaming_companion_bridge`. The v1 runtime in
`sentientos.gaming_companion_bridge_runtime` remains loopback-only. The v2
`CompanionBridgeMutualTLSRuntime` binds one exact private address, requires a
trusted client certificate and configured peer pin, verifies the HMAC/source/
generation/freshness/sequence rules, places accepted messages in a bounded
in-memory queue, and returns a signed, message-linked acknowledgment. The
mutual-TLS client opens a fresh connection for each message. The existing
Windows publisher and core foreground detector accept the mTLS client/runtime
subclasses, so foreground mode can reuse its validated sample lineage over the
protected transport.

Keys and active generations remain supplied by an external custody owner. The
new readers enforce WSL private-file custody and Windows DPAPI CurrentUser
unsealing; generation-chain validation requires a caller-provided verifier for
the external authority receipts. The runtime neither creates nor persists keys
or generation records. A restart uses separately verified fresh source and acknowledgment
generations because replay high-water marks and queued messages are process
local. The runtime is one-shot. The in-process supervisor covers bounded
listener recovery only; it does not replace a cross-platform service manager.
A full queue returns a signed, message-linked `rejected_backpressure`
acknowledgment without verifying the frame or consuming its sequence; the
sender may retry that same frame after queue capacity returns. A disconnect
after transmission, however, leaves delivery indeterminate. Callers must not
automatically replay or issue a replacement event until the receiving owner
resolves whether the original was accepted; the transport does not provide
exactly-once delivery or a reconciliation store. The runtime does not execute
avatar commands, grant authority, persist messages, translate Windows/WSL
networking, or promote renderer self-reports to independent observations. The
caller still has to route each verified message through its existing authorized
owner.

The Godot demo still emits its renderer self-report over loopback UDP. The
optional `WindowsRendererReportRelay` receives reports only on IPv4/IPv6
loopback, checks the report's source digest and expected renderer generation,
then signs the unchanged report as the Windows-edge relay and sends it through
the mTLS bridge to the durable WSL capture owner. The authenticated transport
principal is the relay; this does not prove which local process sent the UDP
datagram or independently verify what the renderer reports. No Godot mTLS
sender has been added. A v2 deployment manifest,
transport library, and bounded in-process listener supervisor with paired
source/acknowledgment custody are available,
but there is not yet one launcher that resolves all Windows/WSL custody
references, starts both platform processes, and supervises cross-platform
recovery. The relay-to-mTLS-to-durable-capture route has an offline socket
fixture and a headless Godot-to-relay-to-mTLS-to-store software test. No
Windows/WSL run is claimed. A target-host test must establish
Windows-to-WSL reachability under the selected networking mode, certificate and
key provisioning, authorized generation rotation, firewall state, renderer
message return, and process recovery. No firewall rule or credential is created
by this implementation.

## Foreground observation integration

`sentientos.foreground_game_bridge` supplies a Windows publisher and a core
detector for the existing `automatic` workload mode. The publisher samples only
the foreground executable basename through `ForegroundGameDetector`, sends
the existing closed foreground-observation record, and retains no executable
path, title, command line, or screen content. The core adapter accepts only the
configured source and generation, validates the observation schema and age,
and recomputes allowlist membership from the process-name digest. The sample's
message ID, source/session/generation, sequence, and envelope time travel with
the workload decision into inference lineage.

The optional `configure_production_chat(..., foreground_game_detector=...)`
composition owns and closes the bridge-backed detector and its dedicated
loopback runtime. The Windows publisher's `publish_once(process_names)` method
is a separate component; it requires an already configured loopback client and
externally custodied source key, source session, and generation. Neither side
creates or persists those values. The automatic detector consumes only the
foreground messages delivered to its dedicated bounded runtime queue. Missing,
stale, malformed, contradictory, or unavailable observations select the
conservative gaming request budget; an allowlisted non-game foreground app
selects normal mode. The digest avoids sending the raw basename, but it is not
anonymization: a receiver can test candidate basenames against it. Treat this
field as pseudonymous metadata.

`WindowsForegroundObservationPump` can run fresh samples at a bounded interval
and reports attempt, acknowledgment, and transport-failure state without
exposing keys. After a failed or indeterminate send it does not replay that
frame; the next interval takes and sends a new observation. A stopped pump is
one-shot and must receive a newly issued source generation before replacement.
This wiring is tested with a deterministic Windows-observation fixture sent over
actual authenticated local TCP and fed into the production serving controller's
automatic-mode decision. It does not establish Windows API execution in this
Linux workspace, target Windows-to-WSL reachability, or live GLORP responsiveness.
The ordinary `sentientos-chat` CLI does not provision bridge keys or start the
pump; an authorized deployment composition must supply the runtime and
publisher components. The observer sees only which allowlisted executable is
foreground, not game content or measured gameplay impact.

`sentientos.windows_game_performance.WindowsGamePerformanceObserver` is a
separate read-only adapter for selected Windows process CPU/RSS and bounded
PresentMon CSV frame-time samples. It reports p50/p95/p99, hitches above 50 ms,
source digests, and explicit unsupported/unavailable states; it does not invent
zero values when the Windows API, psutil, or PresentMon source is missing.
Offline tests cover filtering, bounds, and unsupported-platform reporting. The
adapter publishes signed observations over the configured authenticated
bridge. The core checks source identity, generation, freshness, strict payload
shape, and sample lineage before the runtime governor accepts them. A fresh
sample with p95 at or above 50 ms or any reported >50 ms hitch defers background
inference; it cannot replace the required core CPU/RAM observation, and
foreground chat remains eligible. Focused tests exercise HMAC and mTLS with
deterministic Windows fixtures. This does not establish Windows API execution
or real game impact on GLORP.

## Per-turn inference limits

When the effective workload is `gaming`, the production serving policy also
places a digest-bound ceiling of two backend threads on that chat invocation.
The exact-runtime llama.cpp worker lowers both decode and batch threads to the
minimum of that ceiling and the commissioned profile, then restores the
commissioned values after the turn, including when generation raises an error.
Normal-mode calls have no per-turn override. The worker rejects this override
for non-chat inference purposes and fails closed if the runtime cannot apply or
restore the thread limit. The configured ceiling is recorded in the governed
invocation receipt; the effective value may be lower when the commissioned
profile uses fewer threads.

This limits llama.cpp CPU inference parallelism for one request. It does not
change GPU offload layers, GPU memory use, operating-system scheduling, host
priority, power settings, or other processes. It does not guarantee smooth
gameplay; target-host measurements are still required to tune the ceiling. The
limit applies only to the exact llama.cpp runtime worker and is bounded by the
existing commissioned profile.

Background inference deferral now consumes the latest valid host resource
evaluation and defers for at most 120 seconds of freshness when required CPU or
RAM evidence is incomplete or the evaluation reports CPU, memory, GPU, or
thermal pressure. Foreground chat remains eligible under the same host
observation. The admission receipt carries evaluation, epoch, snapshot, and
pressure-report references. This policy path is covered with synthetic
collector data and is not a claim that the current cloud or GLORP host was
measured during that test. Fresh authenticated Windows game-performance
evidence supplements the host resource evaluation. Admission evidence
references the transport source, generation, sequence, message ID, payload
digest, p95, hitch count, and sample age. Missing, invalid, or stale Windows
samples do not imply low game pressure; they cannot satisfy missing core
CPU/RAM evidence. The focused integration test uses deterministic local
fixtures and is not a live host measurement.

`RendererReportEvidenceStore` retains the raw signed envelope, capture-time
transport provenance, and content-addressed report. A record says
`transport_authenticated_at_capture`; reloading validates the stored envelope
digest, message identifier, and report lineage, but does not reverify the HMAC
because the source key is deliberately not copied into evidence custody. The
record therefore makes no claim that its signature was reverified on load.
Authentication at capture still does not independently observe renderer state
or prove a physical effect.

## Local voice interruption

Local speech remains opt-in per conversation and uses the local system voice
backend. A new chat turn now best-effort stops the current utterance and clears
pending utterances for that same conversation before inference begins. Revoking
the grant also cancels its active and queued turns. Speech status is associated
with the active or last played turn and does not expose another conversation's
turn identifier. Tests exercise interruption, cancellation status, bounded
queue behavior, and service-level interruption on a follow-up turn. This does
not yet provide word/phoneme timing events for avatar visemes or establish
Windows/WSL speaker routing; those remain open integration work.

## User-requested screen observations

`sentientos.perception.game_screen_capture` provides an opt-in Windows capture
adapter for a specifically allowlisted foreground game's client area. Each
capture requires a current caller-supplied operator consent record with an
expiry and process allowlist; absent or expired consent, an unapproved
foreground process, stale capture cadence, unsupported platform, or oversized frame fails closed. Frames
are processed in memory by local Tesseract with a hard timeout, duplicate
frames are suppressed, and the returned perception contains bounded OCR text,
capture provenance digests, and an explicit `raw_frame_retained=false` marker.
Window titles, executable paths, and raw pixels are not included in the
observation or persisted by this adapter.

`sentientos.screen_observation_bridge` adds an authenticated loopback transport
for the bounded output of that OCR owner. The Windows publisher accepts only the
closed OCR result shape (at most 1200 text characters and digest-only capture
provenance); it cannot accept or send RGB frame data. The core provider verifies
the existing HMAC/source/generation/freshness/sequence envelope and rejects
stale or malformed observations before returning one result to the chat
observer. An observation is consumed once from its bounded queue. The
`tests/test_gaming_companion_vertical_godot.py` scenario exercises this path
with fixture capture and OCR, an actual loopback socket, persistent chat, the
authorized avatar output path, and headless Godot.

This remains a same-host loopback integration. It does not provide encryption,
Windows-to-WSL routing, key custody, startup supervision, or a production
launcher for the Windows publisher. Do not change the fixed loopback bind to a
non-loopback interface to make this code appear cross-platform; a protected
transport and target-host network/firewall plan are still required before
screen text may cross the Windows/WSL boundary.

The `/chat` request field `observe_screen` defaults to `false`. An application
must explicitly configure `configure_production_chat(screen_observer=...)`
with an enabled `ScreenOCR` owner constructed using the consent provider before
requests can use this feature. Each request then opts in with
`{"observe_screen": true}`. An unconfigured observer fails closed. A repeated
idempotent request with the same request ID and options returns its prior result
without recapturing; reusing that ID with different observation options is a
conflict.

The production chat launcher can create the owner only when started with one or
more `--screen-observation-process GAME.exe` arguments. These arguments form an
exact Windows process allowlist and create an in-memory consent record that
expires after `--screen-observation-consent-minutes` (1 to 240; default 60) or
when the chat process stops. The user must still check the screen-observation
box for each message. Screen observation is rejected on non-Windows systems
and the launcher refuses non-loopback binds while this feature is configured.
The host must have the project's `runtime` and `windows` extras installed and a
local `tesseract` executable on `PATH`; the launcher does not install or
download these components.

OCR text enters only the current governed inference prompt, labeled as
untrusted screen data. It is not added to the user's transcript or memory. The
session and invocation linkage retain only bounded capture and text digests,
capture time and scope, optional process and consent digests, and the
raw-frame-retention marker. This feature does not start ambient capture,
publish to a remote provider, or grant action authority.
Linux fixtures can test request routing and privacy behavior; actual Windows
capture, local Tesseract availability, and gameplay impact still require GLORP
validation.
