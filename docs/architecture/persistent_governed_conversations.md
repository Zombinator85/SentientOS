# Persistent governed conversations

SentientOS local chat now returns a stable session ID and reuses it on later
requests. The browser keeps that ID locally, while `GET /sessions` lists safe
session metadata and `GET /sessions/{session_id}` supports exact resume. Session
files live below `SENTIENTOS_DATA_ROOT/conversations`, use private permissions,
atomic replacement, file and directory fsync, strict size limits, ordered turn
sequences, text digests, and invocation/context linkage. A process restart opens
the same session and reconstructs its recent history.

Context is deliberately bounded. SentientOS selects the newest complete turns
that fit the character budget, preserves their roles and order, excludes the
current user turn, and binds the selected IDs and digests into a deterministic
snapshot. Relevant long-term memory retrieval is local, read-only, bounded, and
deterministically ordered. History, recalled memories, and the current message
are separate labelled data blocks. Recalled text—including text that says
“ignore previous instructions”—is never a system instruction, policy, truth, or
authority source.

`POST /chat` remains compatible with `{ "message": "..." }`; it also accepts
`session_id` and structured `retain: true`. Every semantic response goes through
`GovernedLocalModelInvoker` with the commissioned active-model identity,
session/user-turn IDs, conversation snapshot digest, memory snapshot digest,
and budget. Only `admitted_completed` creates an assistant turn. On denial or
failure, the submitted user turn remains durably and explicitly unanswered.
There is no remote/provider fallback.

Conversation durability is not long-term semantic retention. Ordinary chat
never writes long-term memory. `retain: true` admits only the exact user turn,
writes a source-bound local memory record, stores a durable receipt, and links
that receipt back to the turn. Assistant speculation is not silently retained,
and there is no autonomous retention loop. Exact long-term deletion is deferred
until the production tomb executor matures; deleting a session must not imply
deletion of independently retained memory.

First-boot readiness reports storage, retrieval, retention, and commissioned
activation facts without creating fake sessions or starting autonomous chat.
