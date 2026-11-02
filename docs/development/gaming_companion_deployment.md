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
chat entrypoint. It explicitly
reports that Windows components and the authenticated bridge were not observed
from the WSL process. The doctor never creates missing paths. Its output is
readiness evidence, not installation, runtime, model, or consent authority.

`blocked` means a required local precondition is missing. `ready_with_warnings`
means the local checks passed but a configured external component or optional
capability remains unobserved. `ready` requires all required observations.
Neither `ready` status creates permission for chat, avatar, screen capture, or
speech effects. The current bridge library is a protocol codec without a
listener, so this checkout cannot report a deployable Windows/WSL session as
ready.

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

For `private_host_firewall`, the manifest requires a firewall-rule reference.
The doctor cannot verify that reference or configure the firewall. Do not bind
the bridge to all interfaces or expose it to a LAN. WSL2 and Windows localhost
behavior must be verified on the target host before choosing a cross-environment
binding.

## Current deployment limit

The authenticated envelope and replay checks live in
`sentientos.gaming_companion_bridge`. `sentientos.gaming_companion_bridge_runtime`
now provides a bounded TCP lifecycle for one envelope per connection. The
listener is fixed to `127.0.0.1`; there is no configurable all-interface or LAN
bind. It verifies the existing HMAC/source/generation/freshness/sequence rules,
places accepted messages in a bounded in-memory queue, and returns a signed,
message-linked acknowledgment. The client opens a fresh loopback connection for
each message. After a listener restart, a caller must construct a new client
with the newly issued acknowledgment generation. A runtime instance cannot be
started a second time; its replacement must receive newly issued source
generations after shutdown.

This is a local transport component, not the split Windows/WSL deployment. Keys
and active generations must be supplied by an external custody/configuration
owner; the runtime neither creates nor persists them. A restart must use a
fresh source generation because replay high-water marks and queued messages are
process-local. External generation custody must issue and supply fresh values;
the transport cannot verify that an externally supplied generation is new. A
full queue returns a signed, message-linked `rejected_backpressure`
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

The current avatar forwarder and Godot demo remain a same-host loopback
demonstration. A target-host test must still establish Windows-to-WSL reachability
under the selected WSL networking mode, independent key/generation custody,
source restart rotation, caller integration, and lifecycle supervision. No
firewall rule or non-loopback bind is created by this implementation.

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
