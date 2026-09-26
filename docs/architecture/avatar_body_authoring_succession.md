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
The configured Blender adapter requires an operator-supplied executable, can bind
its digest, uses `shell=False`, minimal environment, timeout/tree termination,
bounded tails, and exact argv. `scripts/avatar_blender_driver.py` is static
repository code; callers supply JSON only. There is no PATH discovery, generated
Python, `exec`, addon installation, or network fetch. Readiness is read-only and
reports `blender_backend_unavailable` when the configured executable is absent.

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

Established are bounded plans, fixture authoring, inspection, separate CAS
adoption and rollback, exact consequence evidence, World-State projection, and
synthetic causal experiments. Not established are Blender/Godot installation,
physical causation, beneficial adaptation, closed embodied development,
psychological ownership, consciousness, or sentience. A changed strategy is not
automatically an improvement. `neos_blender_bridge.py` remains legacy only.
