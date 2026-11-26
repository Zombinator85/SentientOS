# Persistent governed conversations

SentientOS local chat now returns a stable session ID and reuses it on later
requests. The browser keeps that ID locally, while `GET /sessions` lists safe
session metadata and `GET /sessions/{session_id}` supports exact resume. Session
files live below `SENTIENTOS_DATA_DIR/conversations`, use private permissions,
per-session cross-process file locks with bounded fail-closed acquisition, atomic replacement, file and directory fsync, strict size limits, ordered turn
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
never writes long-term memory. `retain: true` creates an exact source-bound candidate for the independent explicit-retention admission gate. Only an admitted candidate reaches the terminal writer, which stores a raw fragment in the canonical `SENTIENTOS_DATA_DIR/memory/raw` domain and returns a separate execution receipt linked back to the turn. Retention failure leaves the completed chat exchange intact while marking the user turn `retention_failed`. The deprecated `SENTIENTOS_DATA_ROOT` name is only a lower-precedence compatibility alias. A detected `conversation_memories.json` file is inert, reported as legacy data, and never automatically ingested or queried. Assistant speculation is not silently retained,
and there is no autonomous retention loop. Exact long-term deletion is deferred
until the production tomb executor matures; deleting a session must not imply
deletion of independently retained memory.

A user can correct retained statements by supplying their memory IDs with a
new explicit retention request. For example, two corrections to “detailed”
may say “concise” and “medium length”. Revising “concise” to “terse” leaves
both “terse” and “medium length” open. For ordinary personalization, retrieval
keeps competing branches in the verified records together when they fit the record and character
budgets, and omits the whole group when they do not. Both chat prompt paths
identify the unresolved alternatives so a relevant preference can be clarified.
A subsequent correction linked to both alternatives resolves the fork. Direct
links still name the exact older records, which remain available for historical
recall. The restart regression exercises durable retention and prompt assembly
with a simulated model invoker.

First-boot readiness reports storage, retrieval, retention, and commissioned
activation facts without creating fake sessions or starting autonomous chat.
