# Governed avatar-body authoring and succession

## Boundary and causal chain

`sentientos.avatar_authoring` is an explicitly invoked workcell with no cadence
or discovery. It preserves exact adopted predecessor, structured plan, execution
admission, isolated authoring, separate inspection, deterministic comparison,
candidate receipt, separate operator adoption, and compare-and-swap pointer
advancement. Successful tool exit is not a valid candidate, and a candidate is
not the adopted body.

Its schemas are `sentientos.avatar_authoring_plan:v1`,
`sentientos.current_avatar_body:v1`, `sentientos.avatar_authoring_admission:v1`,
`sentientos.avatar_artifact_inspection:v1`,
`sentientos.avatar_authoring_comparison:v1`, and
`sentientos.avatar_authoring_receipt:v1`. Adoption and rollback have separate
receipts and append-only lineage. Receipts bind digests and sizes, never binary
artifact bytes.

## Plans, custody, and backends

V1 operations cover primitive creation, duplication, rename, transforms,
materials, armatures and bones, parenting and binding, shape keys, bounded output
channels, and labels. Unknown keys/kinds, code, shell, addons, URLs, paths,
excessive geometry, and excessive inventories are rejected. Production format
declarations are `.blend`, `.glb`, and `.gltf`; inspection, not suffix, establishes
structure. Artifacts must be nonempty bounded regular files; symlinks and in-place
output are rejected. Each run owns `input/`, `plan/`, `tool/`, `output/`, and
`evidence/` beneath one work ID.

The synthetic author transforms actual bounded fixture bytes; a separate parser
reads successor bytes and is labelled `synthetic_test`, never Blender evidence.
The configured Blender adapter requires an operator-supplied executable and
static driver paths, can pin the executable digest, uses `shell=False`, a minimal
workspace-scoped environment, timeout/tree termination, bounded tails, and exact
argv. `run-one --backend blender` uses the repository-owned authoring and
inspection drivers; its actual operation set covers mesh creation, transforms,
armatures, bones, automatic armature binding, material assignment, and bounded
shape-key deformation. A Blender create_shape_key operation must name 1 to 256
distinct vertex offsets; each index is bounded, each component is finite and at
most 0.25 units, and zero offsets are rejected. The independent inspector reports
changed-vertex count and maximum displacement from the Basis shape, and the
structural comparison requires the requested deformation to survive saving or
GLB export. Binding is accepted
only when the independent inspector sees both an armature modifier and weights
assigned to one of its bones. Unsupported plan operations fail before a Blender
process starts. This adapter accepts native `.blend` and self-contained `.glb`
predecessors. For GLB, the repository-owned driver imports the copied source,
applies the bounded operation set, exports one GLB, then a separate Blender
process imports that output for structural inspection. GLB export omits normals
and UVs because the current operations do not author those channels; the
candidate can contain geometry, skinning, materials, and authored morph shapes,
but has no authored animation clips or textures. The acceptance test also loads
the candidate in Godot and applies a shape key when that engine is installed.
The separate experimental renderer adapter can apply mapped candidate shape keys
and skeleton motion, while reporting missing facial channels as unsupported.
gltf is rejected because external buffer and image
sidecars are not covered by the one-file artifact custody identity. Backend
identity records `configured_candidate_tool`, not production evidence.
Primitive creation is bounded by both an estimated 4,096 vertices per mesh and
65,536 total estimated vertices per plan; the independent inspector records the
actual vertex count and the structural comparison checks it against the request.
`scripts/avatar_blender_driver.py` is static repository code; callers supply JSON
only. There is no PATH discovery, generated Python, `exec`, addon installation,
or network fetch. Readiness is read-only and reports `blender_backend_unavailable`
when the configured executable is absent.

## Adoption, rollback, and embodiment

Genesis is explicit import adoption. Later adoption independently rehashes the
validated candidate, requires explicit approval, and compares the exact current
pointer digest. Staleness fails with
`body_generation_compare_and_swap_failed`. Rollback verifies current and
predecessor custody, atomically restores the pointer, and retains both events.
Only adoption produces the body-manifest observation projected to World-State;
existing longitudinal predicates reconcile generation, asset, and rig. Renderer
handoff is commanded output, neither renderer report nor independent observation.

The one-shot CLI now exposes `plan-validate`, `readiness`, `run-one`,
`candidate-status`, `adopt`, `rollback`, `renderer-handoff`, and `lineage` over
these owners. Every command requires exact paths and identities; none discovers
plans, invokes an unconfigured Blender, adopts automatically, or establishes a
resident cadence.

`sentientos.embodied_consequence` adds a testable developmental causal bridge:
body generation -> preregistered prediction -> action command -> renderer report
-> independent observation -> deterministic attribution/comparison -> governed
developmental interpretation -> controlled later strategy comparison. Renderer
and observer are separate protocol roles. The Godot demo and UDP receiver remain
legacy/demo surfaces and are not production evidence or trusted transport.

Established are bounded plans, fixture authoring, a configured Blender adapter,
independent structural inspection, separate CAS adoption and rollback, exact
consequence evidence, World-State projection, and synthetic causal experiments.
An available Blender executable only demonstrates tool availability, not a
commissioned production renderer or an adopted avatar. Not established are
production Blender/Godot deployment,
physical causation, beneficial adaptation, closed embodied development,
psychological ownership, consciousness, or sentience. A changed strategy is not
automatically an improvement. `neos_blender_bridge.py` remains legacy only.
