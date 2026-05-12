# Federated Improvement Candidate Artifact

The federated improvement candidate is a deterministic, metadata-first object for
representing transmissible improvement evidence under local custody.  It lets a
SentientOS node describe that a locally produced improvement candidate has source
or lineage evidence, verification posture, test or rehearsal labels, risks, and
local review requirements that another node may inspect.

The artifact is intentionally not a federation transport, adoption engine,
scheduler, prompt assembly path, provider invocation path, runtime authority
surface, or remote execution mechanism.  Receipt of the object does not install,
apply, execute, merge, route, schedule, or adopt anything.  Receiving nodes remain
free to inspect, rehearse, adapt, reject, or separately adopt under their own
local governance gates.

Only identifiers, digests, compact labels, statuses, counts, booleans, and coded
warnings are represented.  Raw patch bodies, secrets, prompt text, endpoint data,
client handles, runtime handles, executable payloads, and provider/network/export
runtime material are forbidden and fail closed.

The validation policy fails closed when required local identity, candidate id,
source or lineage evidence, audit verification, immutable verification, and test
or rehearsal evidence are missing or failed.  It also treats auto-adoption,
forced update, remote execution, federation compatibility contradictions, and
local governance bypass markers as contradictions rather than usable evidence.
