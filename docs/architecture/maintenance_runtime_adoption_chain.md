# Maintenance-to-resident-runtime adoption chain

## Scope and result

This report records the implementation at HEAD
`8784f023f114de43f76ccc847fbc228089cfeecd`. The repository has 199 locally
visible commits and is shallow, so history below uses first locally evidenced
appearance rather than claiming an origin. The machine-readable companion is
[`architecture/maintenance_runtime_adoption_chain.json`](../../architecture/maintenance_runtime_adoption_chain.json).
It is review evidence only and grants no runtime authority.

The verified answer is qualified **yes**: stochastic local-model or Codex
machinery can construct candidate files, but it operates inside a deterministic,
operator-derived lease and an isolated worktree. Deterministic controllers own
validation, canonical-repository absorption, same-or-narrower authority
continuity, successor handoff, exact process replacement, and post-exec resident
readiness. This is not a claim that every related governance component is in
that path: `ControlPlaneKernel` and `RuntimeGovernor` are not called by the
successor/continuity/resident controllers, while capability-registry and task
authority definitions describe/admit capabilities rather than serving as the
persisted transition proof.

## Chain of custody

| Stage | Implementation | Owner | Inputs | Evidence produced | Authority | Persistence | Failure posture | Downstream consumer | Confidence |
|---|---|---|---|---|---|---|---|---|---|
| Proposal and selection | `MaintenanceCandidate`, `collect_once`, `select_candidate` | candidate sources; deterministic selector | source evidence, base SHA, policy | canonical set and selection digest | none; proposal only | optional inbox/collector JSONL | fail closed for malformed/ineligible; idle is valid | lease admission | verified fact |
| Custody | `admit_selected_candidate`, `verify_action`, `revoke_lease` | operator grant narrowed by lease controller | candidate, selection, sealed grant, time | immutable lease and journal binding | scoped paths/classes/budgets/time only | external JSON + task JSONL | fail closed | implementation and landing | verified fact |
| Implementation | implementation-agent adapter, local Codex foreman, commissioned local agent | lease-bound deterministic foreman; stochastic worker may author | lease, sealed request, detached worktree | session/result and changed manifest | candidate-worktree writes only | external JSON/JSONL + worktree | bounded model degradation; scope/integrity failures close | validation controller | verified fact |
| Validation | validation plan/runner/controller | deterministic validation controller | lease expectations, independently observed diff, implementation result | stage results and `validation_ready_for_commit` | acceptance only after required commands pass | immutable plan/result + task JSONL | fail closed; bounded corrective retry | commit planner | verified fact |
| Commit candidate | commit plan/create/tree verification | deterministic landing controller | active lease, validation result, exact manifest | detached commit, commit evidence, queued request | creates object, not authoritative ref/runtime | Git objects + immutable external artifacts | fail closed | absorption worker | verified fact |
| Local absorption | `_local_absorption`, `publish_one_maintenance_request` | lease-bound publication worker | commit chain, clean exact checkout, CAS parent | publication result and exact postcondition | **first authoritative repository-state mutation** | canonical ref/index/worktree + result + journal | fail closed; CAS recovery can be incomplete, never silently successful | continuity controller | verified fact |
| Authority continuity | `derive_next`, `_verify_completion`, `_verify_successor` | deterministic continuity controller | closed task, exact absorption, current Git state, predecessor manifest | N+1 generation/profile and continuity receipt | derives only same-or-narrower maintenance authority | immutable external descriptors/receipts | fail closed | handoff owner | verified fact |
| Successor wake handoff | `verified_successor`, `handoff_once`, `pending_handoff` | deterministic successor-generation owner | consecutive generation, receipt, owner locks | successor configuration and six-phase handoff JSONL | transfers wake-owner execution only | external configs/state/journal | fail closed or bounded degradation | resident controller / successor wake owner | verified fact |
| Resident replacement | `request_replacement` and daemon driver | deterministic resident controller | pending handoff, continuity, predecessor provenance, exact repository, sealed launch contract | four pre-exec events and `execve` marker | exact process-image replacement | transition JSONL + provenance | fail closed and terminal | new daemon image | verified fact |
| Resident readiness | `complete_post_exec`, `readiness_guard` | new deterministic daemon image | marker, journal prefix, successor identity/receipt, fresh provenance | readiness receipt and final three events | records successor as authoritative resident | immutable receipt/provenance + fsynced JSONL | fail closed and terminal | future transitions and wake guard | verified fact |

## Inventory and transition details

### Proposal, custody, and mutation

Candidate adapters normalize governed signals, work-item packets, Genesis
metadata, and explicit input. Selection checks deterministic eligibility and
returns `ready_for_scope_admission`; neither act creates a task or lease. Only
`admit_selected_candidate` consumes a digest-valid, temporally valid operator
grant, verifies candidate-set/selection integrity and subset bounds, serializes
admission with a lock, persists an immutable lease, and binds it into the
tamper-evident task journal. One snapshot permits one active lease/attempt.
Revocation is an operator-referenced journal event; expiry and revocation are
checked again at action time.

Therefore, **proposing maintenance does not grant mutation authority**. The
operator grant plus deterministic lease admission does. Even then, mutation is
limited to admitted paths, authority classes, budgets, attempt/retry ceilings,
and time. The local Codex and commissioned-local-model drivers can write
candidate artifacts only through the foreman's isolated detached worktree.
Their final text is evidence about a candidate, not a validation result, Git-ref
update, continuity receipt, or resident-adoption decision. A crash or provider
failure leaves durable session evidence and is bounded degradation; it does not
advance the task.

### Validation and landing

The controller accepts only `implementation_ready_for_validation`, independently
reconstructs changed paths, and constructs fixed argv for Git-diff checks,
lease-declared expectations, behavioral tests, mypy, and audits as applicable.
It records return codes plus output digests and requires every required stage.
A model or candidate **cannot merely claim validation passed**: malformed,
missing, failed, timed-out, or scope-inconsistent results do not produce
`validation_ready_for_commit`. Corrective model work may be requested only
within the existing retry/time lease.

Commit creation uses a separate Git index and yields an unreachable/detached
commit object plus immutable plan/result/request evidence. That is still
candidate state. In the offline production chain, “absorption” is the
`local_fast_forward_base_ref` mode: `_local_absorption` re-verifies every binding,
requires the exact clean canonical branch and parent, compare-and-swaps the ref,
synchronizes the checkout, and verifies the full postcondition. This transition
is reversible only by a separately authorized later Git operation; it performs
no automatic rollback. It is authoritative repository adoption, **not resident
runtime adoption**, and its evidence explicitly says `runtime_adoption_performed`
is false. Remote push/PR modes exist but do not prove the exact local-successor
state accepted by continuity.

### Authority continuity, successor identity, and handoff

The continuity controller rejects weak v1 self-assertions. It reloads the
canonical journal, lease, validation, plan, commit, publication request/result,
and live local Git state; verifies the closed task and exact fast-forward; then
copies the prior manifest with the new base SHA. `_same_or_narrower` forbids new
authority classes/path expansions, removed forbidden paths, higher budgets,
weaker validation, changed executables/refs, or extended time bounds. It writes
an explicit `lineage:generation:N` descriptor and digest-chained transition
receipt. Missing, stale, malformed, partial, branched, or widened evidence
returns `continuity_not_ready`.

State continuity, execution continuity, and authority continuity are distinct:

* **State continuity** is the exact commit parent/ref/checkout and inherited
  configuration state.
* **Authority continuity** is the verified same-or-narrower manifest, generation
  identity, and receipt chain.
* **Execution continuity** is the handoff journal, predecessor quiescence,
  process-instance provenance, exact self-`execve`, marker, and successor
  readiness.

Consequently, **inheriting state does not imply inheriting authority**. The
explicit generation plus continuity receipt is required. The handoff owner then
requires N+1 (never a skipped or caller-selected generation), verifies that
receipt, renders immutable successor component configuration, proves exclusive
owner custody, stops N, and starts N+1. When resident adoption is wired, the wake
handoff pauses after predecessor quiescence until the resident readiness guard
accepts the post-exec receipt.

### Resident adoption and durable evidence

The resident controller accepts only the canonical incomplete handoff at the
quiesced phase, re-verifies consecutive identities and receipt digest, binds the
currently running predecessor process to immutable launch provenance, checks the
exact repository commit/tree, records intent, and calls `os.execve` with the
sealed real interpreter and `python -m sentientosd`. No arbitrary executable,
argv, working directory, `PYTHONPATH`, or `PYTHONHOME` is accepted.

`execve` is the execution switch, but it is not by itself recorded adoption.
The new image must start before the deadline with the exact transition marker,
reconstruct the same pending transaction, capture matching successor launch
provenance, persist a `resident_ready` receipt, and append
`successor_resident_readiness_recorded` followed by
`resident_adoption_completed`. **That final journal transition is the exact
recorded event that makes N+1 the authoritative resident.** Future startup and
handoff logic re-read the transition journal, provenance, generation chain, and
receipt, so this evidence is restart durable. An incomplete or corrupt
transaction blocks startup/maintenance; it does not silently select a runtime.

## Stochastic versus deterministic authority

| Claim tested | Finding |
|---|---|
| Model output cannot self-authorize maintenance | true; the sealed operator grant and lease admission are required |
| Model output cannot self-validate | true; deterministic required-stage results are reconstructed and persisted |
| Candidate runtime cannot self-adopt | true; the predecessor controller, exact `execve`, startup reconstruction, and final journal phase are required |
| Candidate cannot manufacture authority continuity | true; the controller reads canonical external custody and current Git state and rejects weak assertions |
| State inheritance automatically grants authority | false; an explicit same-or-narrower generation/receipt is required |
| Advisory metadata can bypass validation | false on the traced path |
| Alternate runtime can silently become resident | false on the traced path; only canonical `sentientosd` and sealed provenance are accepted |
| Missing continuity evidence can silently succeed | false; generation, receipt, or binding absence blocks |

Proposal is mixed/advisory; implementation is mixed (stochastic authorship
inside deterministic custody); every transition from validation onward is
deterministic and authoritative for its own bounded effect. The architectural
statement “stochastic cognition proposes; deterministic machinery owns
authoritative adoption” is therefore supported by the current traced
implementation.

## Fail-closed analysis

* **Absent/malformed evidence:** fail closed at lease, validation, landing,
  continuity, handoff, and resident stages.
* **Validation failure:** fail closed; a bounded corrective attempt may return to
  candidate implementation, but cannot claim success.
* **Expired/revoked custody:** fail closed at action and absorption checks.
* **Candidate/model crash or provider unavailable:** bounded degradation; no
  downstream authority is produced.
* **Successor mismatch, incomplete handoff, failed continuity, or foreign process
  identity:** fail closed. A recoverable exact phase prefix remains durable;
  ambiguity blocks.
* **Persistence failure:** fail closed where the write reports failure. Git
  absorption is multi-step: a crash after successful ref CAS can leave recovery
  work, but absence of the verified postcondition never counts as success.
* **Quiescence/start/readiness timeout or `execve` failure:** fail closed and
  terminal for the resident controller. There is no automatic rollback to old
  code.
* **Wake scheduling with no candidate/successor:** bounded idle/degradation, not
  an authority transition.

No authoritative transition in the traced chain was found to fail open. The
notable non-transactional gap is operational rather than an authorization
bypass: automatic rollback is deliberately absent after Git CAS or process
replacement, so recovery may require operator action while the system remains
blocked.

## Related surfaces and remaining gaps

The capability registry records these maintenance features and their forbidden
implications. `codex_task_authority_admission` names deterministic principals and
exact effects for continuity, handoff, and resident adoption. Those surfaces
are important governance/admission evidence, but they do not replace the
runtime generation, receipt, provenance, and journal predicates.

The canonical daemon uses `ControlPlaneKernel` to manage lifecycle phase and
uses `RuntimeGovernor` for other restart/repair/control-plane decisions. Neither
is invoked inside this adoption state machine. This separation is a verified
current fact and a documentation gap relative to any stronger claim that all
resident adoption is mediated by those two components. The adoption path is
instead mediated by its sealed configuration, explicit operator adoption,
capability task definitions, leases, exclusive locks, and deterministic local
predicates.

Other remaining qualifications are: POSIX `fcntl`/`execve` is required for live
resident replacement; Windows resident replacement is unsupported; external
operator creation of the initial sealed adoption configuration is outside this
chain; remote publication does not feed exact local continuity; and shallow Git
history prevents claims about the original intent of older self-patching code.
No historical-disposition entry was changed because current evidence did not
justify reclassifying an unrelated preserved runtime.

## Locally evidenced evolution

The shallow boundary `3acae26` (2026-08-21) already contains older maintenance
machinery, so no earlier origin is asserted. The current explicit chain first
appears locally as offline absorption (`ca0dae7`, 2026-09-14), bounded authority
continuity (`938cf44`, 2026-09-14), successor-generation adoption (`ab0fec4`,
2026-09-14), resident adoption (`71a6735`, 2026-09-15), handoff closure
(`22f58d9`, 2026-09-15), automatic continuity derivation (`1ec5907`,
2026-09-15), and disabled-posture hardening (`0efaeb4`, 2026-09-16). Commit
subjects are only locators; the classifications above come from the source and
tests at current HEAD.

## Direct answers

1. The exact chain is candidate normalization/selection → operator-grant lease
   admission → bounded isolated implementation → deterministic validation →
   detached commit evidence → exact local absorption → same-or-narrower
   continuity generation/receipt → successor wake handoff → exact self-exec →
   post-exec readiness receipt and completed adoption event.
2. Candidate files first become authoritative **repository state** at the exact
   local base-ref CAS plus verified checkout postcondition. They become
   authoritative **resident state** only at `resident_adoption_completed`.
3. Stochastic output cannot directly cross either boundary.
4. Authority continuity is demonstrated by canonical closed-task and local-Git
   proof, a same-or-narrower N+1 manifest/profile, and a digest-chained receipt
   binding predecessor, successor, validation, commit, landing, and closure.
5. Yes. State, authority, and execution continuity have separate identities and
   evidence.
6. Exact self-exec starts execution under N+1; the persisted final
   `resident_adoption_completed` phase after a valid readiness receipt makes it
   the recorded resident.
7. All authority-bearing gates named above fail closed on missing, stale,
   malformed, mismatched, expired, or failed proof.
8. Model/provider absence and “nothing eligible yet” are bounded degradation or
   idle. Recovery is not automatic rollback; partial exact prefixes remain
   incomplete and blocked rather than succeeding.
9. Initial operator adoption is out of band; Windows live replacement is absent;
   rollback is operator-owned; `ControlPlaneKernel`/`RuntimeGovernor` do not
   directly mediate this state machine; pre-shallow-boundary origins are unknown.
10. Yes, with the precise qualification that models can perform lease-bounded
    candidate writes, while deterministic machinery owns all authoritative
    validation, repository adoption, authority continuity, and resident adoption.
