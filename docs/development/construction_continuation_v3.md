# Construction continuation index v3

## Purpose

The v2 construction root shards segment records but keeps every shard descriptor
in `work/construction/index-v2.json`. The root therefore grows with construction
history and requires the full historical index on each append. V3 replaces that
mutable descriptor list with a bounded continuation head and immutable,
predecessor-linked shard files.

## Immutable anchor and chain

`work/construction/index-v3.json` names the exact v2 root by path, byte count,
SHA-256, Git blob SHA, latest sequence, and latest segment digest. The verifier
first verifies that exact v2 root with the existing v2 custody verifier. This
retains verification of the frozen v1 index, every v2 shard, all historical
segments, evidence files, checkpoint bindings, and the legacy journal.

V3 stores no segment array and no shard descriptor array. The head contains only
the immutable v2 anchor, the current sequence and segment digest, the shard
count, one descriptor for the latest shard, and the current checkpoint binding.
The latest v3 shard points to its predecessor by path and both content digests.
Verification walks backward until it reaches the exact v2 root identity, then
checks the collected chain forward for sequence coverage, segment predecessor
bindings, bytes, hashes, evidence identities, provenance, and checkpoint
consistency. Shard paths have fixed-width sequence fields; the verifier bounds
numeric fields and head bytes.

Each update creates one immutable shard and replaces the small head and active
checkpoint. Existing v1 and v2 roots, checkpoints, segments, evidence, and
shards remain byte-identical. The source preflight requires an initial v2-to-v3
head to bind the parent v2 root exactly. Later v3 updates must preserve that
anchor, every existing segment entry, and every prior shard byte.

## Interruption recovery

Shard generation is deterministic from the predecessor descriptor and bounded
segment batch. A retry from the unchanged predecessor can recognize identical
already-written shard bytes and regenerate the same head/checkpoint update;
conflicting bytes fail closed. A Git tree publishes the shard, head, and
checkpoint together. A local interrupted partial state remains unverified until
reconstruction completes. A head that
references a missing, malformed, or digest-mismatched shard is invalid. The
verifier does not infer missing links from directory contents and never skips a
predecessor.

## Publication boundary

V3 is prepared locally against the last verified v2 main root. The locally
verified sequence 868 candidate remains separate and unchanged. The previous
platform denial applies to uploading the full `index-v2.json` blob for sequence
868; it must not be bypassed. A v3 migration can be integrated only through the
normal review process after the platform permits the exact new candidate,
including its bounded `index-v3.json` head, predecessor shard, verifier, tests,
and source-preflight changes. The exact index-v2 denial does not authorize a
different v3 payload or destination action.
