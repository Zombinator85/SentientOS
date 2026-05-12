# Federated Improvement Intake Receipt

A receiving-node federated improvement intake receipt is a deterministic,
metadata-only custody artifact for `FederatedImprovementCandidate` evidence. It
answers whether a candidate that arrived at a node is eligible for local
inspection, local rehearsal, local adaptation, rejection, or a separate local
governance review queue.

The receipt is deliberately not an adoption artifact. It does not install,
apply, execute, merge, route, schedule, transport, prompt, export, call a
provider, or expand runtime authority. It records only node IDs, candidate IDs,
digests, compact statuses and decisions, gate code labels, verification labels,
booleans, and lineage references by ID or digest.

Local custody is preserved because the producing node's candidate remains
external evidence and the receiving node records only an intake classification.
Any later adoption must occur through the receiving node's own governance,
audit, immutability, compatibility, and canonical control-plane gates. A remote
candidate cannot force an update, bypass a local gate, grant remote authority,
or carry endpoint, client, secret, prompt-text, raw patch, or executable payload
material inside the receipt.

Fail-closed intake statuses distinguish incomplete metadata, contradicted
metadata, local-review holds, explicit rejection, ready-for-inspection,
ready-for-rehearsal, and ready-with-conditions outcomes. Decisions remain
bounded to inspect-only, rehearse-locally, adapt-locally, reject-candidate,
hold-for-operator-review, or queue-for-local-governance-review.
