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
`sentientos.gaming_companion_bridge`; that module does not open sockets, custody
keys, reconnect, or manage component lifecycles. The current avatar forwarder
and Godot demo remain a same-host loopback demonstration. Startup, health
monitoring, reconnect, shutdown, and actual Windows/WSL communication remain
unfinished and must be proven on the target machine.
