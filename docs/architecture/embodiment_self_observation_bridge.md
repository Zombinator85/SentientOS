# Embodiment self-observation bridge

## Established boundary

`sentientos.embodiment_self_observation:v1` is the modern, bounded,
non-authoritative evidence envelope. Every observation carries an explicit source
identity and schema, semantic digest, observation time, provenance class,
freshness, and production/rehearsal/synthetic posture. The accepted families are
body manifests, sensor and actuator observations, commanded avatar state,
renderer-reported state, independently observed state, and fulfillment
observations. Missing families remain absent; files are never discovered
ambiently.

`sentientos.avatar_body_manifest:v1` describes exact technical machinery:
installation/body and asset identities, artifact and rig digests, format,
renderer interface, coordinate convention, bounded bone/expression/motion/viseme
inventories, sensor/output bindings, authoring provenance, generation, and
optional predecessor digest. It contains no mesh, media, executable script, or
authority.

`RuntimeMaintenanceSurfaces` accepts an explicitly injected
`EmbodimentEvidenceOwner`. When absent, embodiment composition is inert. When
present, validation is fail-closed and records use the existing `embodiment` and
`fulfillment` World-State source kinds. Cognition may select those kinds through
its existing allowlist. Reconciliation still occurs after cognition, so only a
previous tick's embodiment claims can enter the cognitive self-model projection.

Commanded, renderer-reported, independently observed, and proven-consequence
states are mechanically separate. A command does not create observation; a
renderer report does not prove physical effect; only qualifying fulfillment
evidence may carry effect proof. Sensor presence and health are separate and a
healthy claim requires explicit presence.

The historical `ResidentKernel.EmbodimentView` and simulated embodiment daemon
remain legacy/simulation sources. They may be adapted only from an explicitly
verified injected checkpoint; they are not the canonical owner. `avatar_state.py`
and `godot_avatar_receiver.py` are compatibility/output-command surfaces,
`avatar_pose_engine.py` and the Godot avatar are demo surfaces, and old
Neos/Resonite/ritual paths are legacy. None becomes self-knowledge merely because
it exists.

## Controlled experiment

The acceptance experiment uses production composition classes with synthetic,
visibly labelled evidence: A has body generation 1, rig R1, camera present and
healthy, and independently observed idle; B changes only camera health to false;
C restores the exact A evidence. Deterministic snapshot deltas, self-model
supersession, reconstruction after restart, and the prior-tick projection firewall
are checked. Structured answers are scored externally for supported correct and
incorrect claims, unsupported assertions, abstentions, provenance, and
command/observation handling. Model prose never determines success.

## Blender authoring handoff

A later workcell must consume an exact manifest and structured modification plan,
operate only in a dedicated authoring workspace through an exact configured
Blender binary and repository-owned bounded driver, and never execute arbitrary
model-authored Python. It must inspect the source artifact; enumerate bounded
armature, bone, shape-key, material, and mesh summaries; produce and independently
reinspect a successor; compare intended and actual structure; emit an authoring
receipt; and require explicit adoption before advancing body generation. The
receipt must bind predecessor/successor artifacts and manifests, tool identity,
workspace, plan, inspection results, and rollback target. Renderer test feedback
and independent observation remain later evidence, not consequences inferred from
authoring success.

## Not established

This bridge does not establish physical embodiment, renderer success without
observation, Blender self-authorship, beneficial adaptation, psychological body
ownership, consciousness, sentience, or any GUI, camera, microphone, filesystem,
network, renderer, Blender, communication, locomotion, or hardware authority.
