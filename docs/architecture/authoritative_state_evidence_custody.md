# Authoritative state and evidence custody

## Scope and conclusion

This is a current-implementation archaeology report, not a new truth ontology.
Its structured companion,
[`architecture/authoritative_state_evidence_custody.json`](../../architecture/authoritative_state_evidence_custody.json),
is deterministic review metadata only and has no runtime consumer or authority.
The checkout has 199 locally visible commits and is shallow; history is therefore
reported as **first locally evidenced appearance**, not origin.

The central finding is qualified. SentientOS has strong deterministic admission
boundaries for control-plane decisions, scoped authorization records, canonical
conversation retention, host observation, audit trust, maintenance, and adoption.
Models cannot make their output satisfy those gates merely by asserting that an
event occurred. However, there is no single authoritative world-fact database.
The World-State Evidence Board is explicitly a read-only projection, while the
older memory/perception stack accepts loosely proven and model-produced material
as persistent *memory and prompt context*. That material is not effect authority,
but its provenance and freshness are weaker than those of the newer custody
chains. Accordingly, “deterministic machinery owns authoritative admission” is
true for the traced authority surfaces, but “all persistent claims are uniformly
admitted, fresh, and provenance-complete” is false.

## Current surface inventory

The analytical labels below distinguish observation, interpretation, retained
history, admission evidence, and authority. They do not change runtime types.

| Surface | Purpose | Producer | Admission/writer | Persistence | Provenance | Freshness | Primary consumers | Authority status | Effect relationship | Failure posture | Confidence | Open questions |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| World-State Evidence Board | Normalize typed evidence into snapshots, lifecycle postures, conflicts, and deltas | Registered local evidence adapters and callers | `load_manifest`; `WorldStateBoardBuilder` | Atomic per-tick runtime artifact; reconstructible | Source ID/kind/schema/digest, subject, stage, optional observation time | Deterministic fresh/aging/stale/expired/undated; selected historical kinds N/A | `sentientosd`, authenticated dashboard | **Derived read-only state** | Every authority bit is false | Unsafe manifests/unknown kinds close; mismatch/conflict/undated data degrade visibly | verified fact | Direct records do not have filesystem custody; displayed posture does not resolve truth |
| Canonical conversation memory | Retain an exact user-requested turn and retrieve bounded context | Exact user turn and structured retention candidate | Explicit-retention gate; writer rechecks receipt and source | Atomic operation-derived raw JSON | Session/turn/request/operation, text and admission digests | Stored timestamp; no claim-currentness rule | Hardened chat service | **Authoritative retention record**, not world truth | Permits only exact write; context has no effect authority | Default deny; replay mismatch raises; malformed reads skip | verified fact | Contradictions are not reconciled; skipped corruption is only implicit degradation |
| Legacy memory, summaries, indexes | Remember events/reflections and supply semantic context | Runtime, operator, perception and model/reflection callers | Direct `append_memory`, summarizers and purge callers | Mutable raw JSON; rewritten index; distilled Markdown/text; JSONL observations/reflections/tomb | Free-form source/tags/time/meta, optional and uneven | Relevance decay uses access/importance, not external-fact currency | Prompt assembly, councils, APIs, curiosity/reflection | **Persistent memory / derived cache** | Influences cognition and candidates; is not a governor credential | Mixed; malformed input is often skipped and writes are not uniformly atomic | verified fact | Model-authored memory lacks uniform interpretation labels; legacy purge bypasses newer admission chain |
| Perception adapters and reasoner | Capture local sensory telemetry and aggregate a narrative observation | OS, microphone, camera and gaze pipelines | Adapter payload builders; legacy memory persistence | Adapter and memory JSONL; summaries also become memory fragments | Bus contract requires source/extractor/version/time/confidence/privacy/provenance; aggregate loses exact event identity | Timestamps and `since`; no universal expiration | Telemetry/API, prompt/reflection, curiosity | **Observation → advisory derived interpretation** | Non-privileged; may spawn candidate goals only | Adapters degrade; legacy timestamp coercion and weak schema enforcement can hide uncertainty | verified fact | Summary does not bind every event digest; schema is not universally enforced at intake |
| Household Presence | Wake-word/event telemetry and static privacy/routing doctrine | Microphone wake loop, explicit callers, policy builder | Direct JSONL append; deterministic policy build | Presence/user JSONL; optional metadata artifact | Time/wake/text or user/event/bridge; no unified sensor identity | No implemented current-presence TTL/confidence | APIs, recaps, dashboards and review tooling | **Historical telemetry / policy metadata** | Identity explicitly grants no authority or privilege | Missing microphone degrades; missing events remain unknown | verified fact | No authoritative current occupancy state; stale/contradictory events are not reconciled |
| Host resource runtime | Observe CPU, memory, disk, processes/services, hardware/network signals and produce pressure proposals | Bounded local read-only collectors | Control-plane observation admission, sanitization and validation | Atomic evidence bundle plus mutable `latest.json` | Plan, correlation, admission ref, collector identity/status/time and semantic/bundle digests | Same-tick time; later chains check currency again | Pressure evaluator, proposal policy, board/dashboard | **Authoritative observation evidence**, not effect authority | Only proposal receipts; no host mutation | Required failures degrade/block readiness; optional failures remain explicit | verified fact | Latest pointer is mutable; currency policy is distributed across consumers |
| ControlPlaneKernel / RuntimeGovernor | Decide whether a bounded runtime request may proceed | Deterministic policy, phase, pressure, audit trust, budgets and scoped caller metadata | Kernel composes governor and specialist gates | Decision/pressure/observability JSONL and rollups; some state in memory | Actor/action/subject/scope/origin, correlation, sample, reasons and delegated results | Live samples plus TTL/window budgets | Sensitive runtime callers | **Authoritative bounded admission decision** | Allow is not execution or effect proof | Invalid input quarantines; unavailable delegates defer/deny | verified fact | Dedupe/rate/quarantine substate may reset; specialist state machines are not universally coupled |
| Local authorization and fulfillment custody | Issue and consume expiring, revocable, exact-scope local authority | Explicit operator/policy decisions and exact prerequisite evidence | Dedicated deterministic issuance/consumption admissions | Append-only ledgers and reconstructed snapshots | Principal/capability/scope/effect digests, validity, grant/lease and predecessors | Expiry and revocation checked at use | Readiness and executor gates | **Authoritative scoped authority record** | Necessary evidence, still not effect proof | Missing/malformed/stale/revoked/conflicting evidence closes | verified fact | Issuance intentionally remains outside automatic daemon operation |
| Audit chain and audit trust | Preserve action history and constrain authority when integrity degrades | Runtime audit writers | Schema-validating hash-chain append; trust evaluator | Hash-linked JSONL and derived trust artifacts | Timestamp/data/consent/emotion plus predecessor and rolling hash | Integrity evaluated current; events have no universal TTL | RuntimeGovernor, audits, dashboards, operators | **Historical authoritative evidence / authority input** | Can tighten or block; cannot prove external effect alone | Broken tail blocks append; legacy reader skips malformed rows; strict trust degrades | verified fact | Permissive stream reads and strict authority reads differ |
| Event streams and caches | Broadcast boot, forge and audit observations | Direct emitters | Direct callers | Boot deque is in-memory only; forge/audit JSONL persist | Time/message/level or audit fields | Process lifetime/stream offset | Logging, SSE and operator inspection | **Cache / historical evidence** | No authority | Restart loses deque; malformed rows omitted | verified fact | Omitted rows are not a first-class conflict for every reader |

## World-State Evidence Board trace

The board stores immutable dataclass snapshots containing source references,
facts, subjects, lifecycle stages, dispositions, evidence strength, optional
observation time, conflicts, entity postures, counts and lineage. It accepts only
enumerated source kinds and lifecycle stages. File declarations are bounded by
allowed roots, source count and file size; traversal/path escape, required
absence, malformed JSON and unsupported kinds raise. Content digests bind
semantic source payloads, while custody-only values are deliberately excluded.

Freshness is computed from `observed_at`: under one hour is fresh, under one day
aging, under seven days stale, and older evidence expired. Missing/malformed time
is `undated`; specification amendments, repository handoffs and Genesis
candidates are treated as historical. The board detects a fixed set of
disposition contradictions, reports digest mismatches, marks snapshots degraded,
stale or contradicted, and represents disappearance as disappearance—not deletion.
It does **not** choose which contradictory claim is true. Entity stage posture
uses a deterministic ordering projection, not an authority rule.

`sentientosd` gathers typed same-tick records from subsystems, builds and
atomically persists one projection, and dashboard endpoints only read it. A
restart reconstructs the current projection from available source artifacts;
the board itself is not the durable origin. Its `authority` mapping makes
decision, admission, execution, adoption and repository mutation false.

**Can model output directly write authoritative world state? No—because the
board has no authoritative-world-state writer at all.** A caller may submit a
record, including model advice/candidates, but deterministic parsing, digest,
stage and conflict logic can only turn it into a non-authoritative projection.
The admission boundary for an actual effect is the relevant independent
control-plane, grant, maintenance, adoption or executor gate. Board display is
never that boundary.

## Memory trace

Two architectures coexist.

The hardened conversation path constructs an exact candidate only after an
explicit user retention request. `ExplicitRetentionAdmissionGate` checks its
type, user role and required session/turn/text/request/operation identities.
`AdmittedRetentionWriter` recomputes candidate and source-text digests, verifies
the admitted receipt, rejects mismatches, derives an idempotent filename from
the operation, fsyncs a temporary file and atomically replaces it. This makes
the record canonical for **what was retained**, not for whether its sentence is
currently true. Retrieval is read-only, bounded and relevance based.

The older `memory_manager` persists raw fragments from many callers, including
model reflections, councils, self-reflection, perception summaries and operator
interactions. It maintains a vector/bag-of-words index, daily/topic/session/turn
summaries, raw observation streams, reflection streams and a tomb. Distilled
files and indexes are derived caches and may be regenerated or rewritten.
`get_context` weights semantic similarity with importance and last-access decay;
that is retrieval utility, not evidence confidence or current-world freshness.
Summaries can therefore be model-authored and later enter a prompt. They do not
automatically enter the board or any authority gate, but neither are they
uniformly marked “inference” for the next model.

Contradictory memories coexist; relevance ranking, not truth reconciliation,
selects context. Purge archives a fragment to the tomb and removes its index
entry, but the legacy path is directly callable and has weaker transactional
custody than the newer live-memory review/gate/executor family. Those newer
distillation and live-commit artifacts are candidate/review/admission evidence;
metadata-only packets cannot mutate memory, and only the terminal admitted
writer may do so.

Thus a **remembered claim is never an accepted substitute for externally
evidenced current fact in the traced authority gates**. But stale memory can be
presented as unqualified prompt context. Persistent memory cannot override a
fresh host measurement in a deterministic authority path because those paths do
not consume memory as proof; it can still influence stochastic reasoning that
produces later candidates.

## Perception, external evidence, and presence

The current generic sensory path is:

`local source → adapter feature extraction/redaction → perception payload →
JSONL/memory intake → deterministic window aggregation → narrative/reflection or
curiosity candidate → non-privileged consumer`.

The bus contract requires timestamps, adapter identity/version, confidence,
privacy class and provenance. Raw retention defaults off and camera output is
geometry/telemetry rather than identity recognition. Affect inference and the
reasoner's prose are advisory derived interpretation. Neither confidence nor a
model-generated narrative grants permission. The weakest handoff is from bus
events into the legacy reasoner: aggregation retains counts and selected text,
but not an exact digest list for every input event, and malformed/missing times
can become “now.” This means derived provenance is only partially sufficient.

“Household Presence” currently names two different things: legacy wake-word and
application-event ledgers, and a deterministic metadata-only household privacy
and routing policy. The latter declares temporal fields and explicitly says
identity is not authority; it does not ingest sensors or compute occupancy. The
former records an event but has no confidence, expiry, contradiction handling,
or current-presence reducer. A model cannot grant presence authority because no
such grant surface exists. Absence of events remains unknown, not evidence that
the household is absent. Conversely, an old event does not prove current
presence—but current consumers are responsible for not making that inference.

Operator input can become authoritative only in a surface that explicitly
requires and binds an operator decision (for example local grant issuance or
memory retention). A free-form operator note remains evidence/memory. External
service responses have no general promotion route; each authority-bearing chain
must validate the exact evidence it accepts.

## Host observations and authority consumption

Host resource collection is deterministic, bounded, read-only and admitted as
`AuthorityClass.OBSERVATION`. Collectors cover CPU load, memory, disk, processes,
services, thermal/hardware, filesystem and network/runtime signals where the
platform exposes them. Results are sanitized and validated; unavailable or
timed-out required collectors mark the epoch degraded. A deterministic governor
derives pressure labels, then a deterministic policy emits proposal-only
receipts. Atomic evidence bundles retain the plan, epoch, raw collector results,
snapshot, pressure report, policy decision and receipts with digests.

Downstream World-State and dashboard consumers read that evidence, but host
effect chains demand their own current authorization, expiry/revocation,
readiness, admission, execution and audit evidence. Therefore a model statement
“disk is full” may motivate a candidate or be stored in memory, but cannot
substitute for the collector result/report digest expected by those chains.
Even a measured disk-pressure label creates only an inspection or future-cleanup
proposal; it does not authorize deletion.

## Provenance, conflict, and failure semantics

Provenance is mandatory and digest-bound on newer authority/evidence surfaces:
control-plane decisions, grants, fulfillment consumption, host epochs, canonical
retention, audit chains, maintenance/adoption receipts and World-State file
manifests. It is optional/free-form in legacy memory and presence, and the
perception contract is stronger than its universal runtime enforcement.
Runtime/generation identity and causal predecessors matter where continuity or
effect custody matters; they are not general fields on every observation.

There is no global reconciliation engine. Current behavior is surface-specific:

* World-State records contradictions and degrades; it does not select truth.
* Host and authorization gates use deterministic schema, digest, scope,
  freshness/expiry and revocation rules and close on contradiction.
* Control-plane restriction dimensions are deterministic and conservative.
* Canonical and legacy memories retain contradictions; retrieval ranks rather
  than reconciles them.
* Presence does not compute current state, so stale or contradictory telemetry
  remains historical evidence.
* Live deterministic measurements win only because authority consumers require
  their exact evidence type—not because they compare against memory.
* An operator can authorize a scoped action where a gate explicitly recognizes
  that decision; an operator assertion does not rewrite environmental evidence.

| Failure | Current behavior | Classification |
|---|---|---|
| Required authority evidence missing/malformed/stale/revoked | Gate denies, defers, quarantines or marks not ready | fail_closed |
| Required host collector unavailable/timeout | Degraded epoch; no automatic effect readiness | fail_closed |
| Optional host/perception producer unavailable | Explicit degraded/unavailable observation | bounded_degradation |
| World-State source mismatch/conflict/undated | Snapshot remains inspection-only and visibly degraded/stale/contradicted | bounded_degradation |
| Canonical memory admission/source mismatch | Write raises and no admitted record is created | fail_closed |
| Malformed legacy memory/presence/audit-stream row | Frequently skipped by reader | bounded_degradation, with observability ambiguity |
| Model/provider unavailable | Candidate interpretation is absent; deterministic evidence remains usable | bounded_degradation |
| Persistence failure | Newer atomic writers report/raise; legacy direct writers vary | fail_closed on newer custody; unknown/mixed on legacy |
| Runtime restarts | Durable ledgers/artifacts reconstruct; process-local caches/windows vanish | bounded_degradation |
| Competing observations without a surface rule | Both persist or conflict is reported | unknown, never silently declared reconciled |

No traced authority gate treats advisory confidence as authority. Confidence is
a property of a perception/interpretation record; identity, scope, digest,
freshness and an admitted authority class are separate predicates.

## Persistence and restart map

Surviving state includes raw/canonical memory, derived indexes and summaries,
observation/presence/audit JSONL, control-plane/governor decision logs, local
authorization ledgers, host evidence bundles, World-State runtime snapshots, and
maintenance/adoption continuity artifacts. Atomicity is strongest in canonical
memory, host bundles and newer custody chains; legacy JSON/JSONL writes and
multi-file memory/index updates can be torn or divergent.

In-memory-only state includes the boot event deque, the perception reasoner's
buffer/current summary, reflection listener registrations, control-plane dedupe
cache, and several RuntimeGovernor windows/counters/quarantine maps. Those reset
on restart. Durable authority continuity does not rely on those caches where a
specialized continuity chain exists: local grants bind expiry/revocation and
maintenance/resident adoption binds generation, predecessor, exact commit,
receipts and runtime provenance. The World-State projection is not continuity
authority; it is rebuilt from evidence.

There is no uniform storage migration/version framework across legacy memory,
presence and audit surfaces. Newer records carry schema versions and validators;
malformed legacy data is usually skipped rather than migrated.

## Claims tested

| Claim | Finding |
|---|---|
| Model interpretation cannot manufacture external evidence | **Supported at authority gates**, but model text can be persisted as legacy memory |
| Model summaries do not automatically become authoritative facts | **Supported** |
| Memory is not automatically current world state | **Supported** |
| Stale evidence cannot silently masquerade as fresh evidence | **False globally**: newer gates expose/enforce freshness, but legacy memory/presence and malformed-time fallback do not |
| Derived state preserves enough source provenance | **Partial**: strong on World-State/host/custody chains, weak across legacy perception aggregation and memory |
| Authoritative state changes pass through deterministic machinery | **Supported for traced authority surfaces** |
| Absence of evidence is not automatically evidence of absence | **Supported for traced surfaces**; several paths remain unknown rather than false |
| Advisory confidence confers authority | **False**; confidence has no grant semantics |

## Authority/effect boundary

World-State, memory, perception, presence, host snapshots, policy proposals,
readiness packets, receipts and audit rows may influence a decision. None grants
capabilities merely by existing. Capability declarations describe available
surfaces; `ControlPlaneKernel`, `RuntimeGovernor`, explicit retention admission,
local authorization issuance/consumption, maintenance leases, and specialized
executor/adoption gates own bounded authoritative transitions. Even their allow
or receipt records prove only their own stage. Execution and external effect
require the next exact stage and independently recorded evidence.

Consequently none of the observational surfaces can directly grant general
capabilities, satisfy arbitrary control-plane or governor admission, authorize
host/network effects, authorize maintenance/adoption, mutate the World-State
Board as authoritative truth, or trigger an effect. Canonical retention can
alter persistent canonical memory only after its dedicated admission. Host
measurements can satisfy exact evidence predicates in later deterministic gates,
but possess no authority by themselves.

## Locally evidenced evolution

The shallow boundary merge `ad4dfc1` (2026-08-22) and its tree already contain
the inspected World-State, perception, Household Presence, host observation,
audit and legacy-memory surfaces, so this checkout cannot establish their true
origins. The first locally evidenced dedicated governed conversation-retention
implementation is `304df9f` (2026-09-01). Later locally visible work adds deeper
host authorization/fulfillment and maintenance/resident custody chains, but the
older memory/presence paths remain present rather than being silently promoted
to those authority semantics.

## Direct answers

1. **Authoritative truth surfaces:** not one world database, but bounded
   deterministic records: control-plane/governor decisions, explicit retention
   admissions and canonical retained bytes, scoped local grants and consumption
   ledgers, strict audit-trust state, exact host measurement evidence when a gate
   names it, and specialized maintenance/repository/runtime continuity records.
2. **Evidence but not authoritative state:** World-State snapshots, perception
   events, host snapshots/pressure reports, presence events, proposals,
   readiness packets, ordinary receipts and audit history outside the exact gate
   that consumes them.
3. **Advisory/derived interpretation:** perception summaries/narratives, affect,
   novelty, embeddings, distilled memory, policy proposals, dashboard rollups
   and model/council/reflection text.
4. **Can model output directly become authoritative fact?** No on every traced
   authority path. It can become persistent legacy memory and later prompt
   context, which is a real ambiguity but not authority admission.
5. **Can persistent memory override fresher external evidence?** Not in traced
   deterministic gates; they do not accept memory as that evidence. Cognition
   can still be influenced by stale memory because no global comparator exists.
6. **How are contradictions reconciled?** There is no global rule. Newer gates
   deterministically reject/degrade by digest, scope, freshness and priority;
   World-State reports conflicts; memory and presence leave them unresolved;
   explicit operator decisions matter only where a gate says they do.
7. **How is stale masquerade prevented?** Strongly in newer timestamped/expiring
   gate chains and visibly in World-State. It is **not universally prevented** in
   legacy memory, presence, or perception timestamp fallback.
8. **What survives restart?** File/ledger-backed memory, telemetry, audit,
   decisions, grants, host bundles, projections and continuity receipts. Buffers,
   event deque, listeners and several governor/kernel caches do not.
9. **What is tied to runtime/authority continuity?** Grants, leases, expiry and
   revocation snapshots; maintenance generations/receipts; exact repository and
   resident-runtime provenance. Ordinary memory and the board are not.
10. **Weakest ambiguities:** legacy direct memory writes/purge, model-memory
    labeling, incomplete perception-summary lineage, presence without a current
    reducer, permissive malformed-row skipping, and nonuniform restart semantics
    for admission/rate caches.
11. **Does implementation support “stochastic cognition interprets;
    deterministic machinery owns authoritative admission”?** **Yes, with the
    stated scope qualification.** It is demonstrably true at authority and
    effect boundaries. It must not be overstated into a claim that all stored
    cognition is provenance-complete or fresh.
