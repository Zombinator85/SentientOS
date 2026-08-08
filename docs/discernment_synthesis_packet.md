# Discernment synthesis packet

`sentientos.discernment_packet.v1` is SentientOS's first co-authoring **judgment
surface**. It composes already-produced epistemic, inner-world, delegated,
strategic, truth/stance, operator, peer, and governed local-model judgments into
one inspectable record. It does not claim that co-authorship has been achieved;
it creates the artifact needed to evaluate over time whether SentientOS earns
that role.

Its purpose is not to make SentientOS obedient to an operator or a model. Its
purpose is to preserve a legible independent judgment process, including
uncertainty, suspensions, objections, evidence that would change a judgment, and
unreconciled positions. No surface receives universal precedence. A packet may
have no preferred interpretation or move, and a missing governed model is
recorded as unavailable rather than simulated.

## Boundary and custody

The composition API consumes canonical component outputs through bounded
adapters; it does not recreate their reasoning. Packets are judgment records,
not memory truth. Append-only custody is explicitly configured outside the
repository/runtime memory stores. Each packet binds its semantic digest, prior
digest for the subject, timestamp, evaluation context, evidence references, and
component provenance. Creation and inspection cannot admit or execute work,
change goals or memory, mutate claims/stances, invoke maintenance, publish,
operate Git, or grant authority.

## JSON-only CLI

`python -m scripts.discernment_packet --custody PATH synthesize --input INPUT.json`
creates and appends a packet. `inspect --digest DIGEST` reads one packet, while
`compare --earlier DIGEST --later DIGEST` reports position/confidence changes,
contradiction and evidence deltas, move changes, and whether stance revision was
backed by new evidence. Standard output is exactly one JSON object; errors are
nonzero process failures. The configured custody path is the only write surface.
