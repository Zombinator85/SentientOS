# Present-day effect authority archaeology

This is descriptive architecture evidence, not a registry, grant, policy, admission,
or execution surface.  It records the implementation inspected on the current branch.
The machine-readable companion has `authority: none` and no runtime consumers.

## Finding in one sentence

SentientOS does **not** have one universal intent-to-effect chain.  Newer sensitive
paths use deterministic, fail-closed admission, but several canonical, compatibility,
operator-invoked, daemon, and developer-workflow modules perform effects through their
own checks or no ControlPlane check.  Therefore “stochastic cognition may propose;
deterministic machinery owns real effects” is verified for the governed local-model and
Genesis paths, but is not a repository-wide enforcement invariant.

## Authority inventory

| Surface (primary symbols) | Role and callers/consumers | State/evidence read and written | Authority, boundary, failure and restart |
|---|---|---|---|
| `sentientos/capability_registry.py` (`CapabilityRecord`, `CapabilityRegistry`, `build_default_capability_registry`) | Static, metadata-only inventory used by proof/dashboard/update builders. Records implementation posture, authority labels, requirements and forbidden implications. | In-memory immutable records; serializers/digests and explicit update functions produce derived snapshots. The separate `_DISABLED_CAPABILITIES` map is process-local diagnostic state. | Descriptive only: existence, `implemented`, or an authority label is not admission. Unknown validation values fail validation, but the registry is not consulted by general actuators. Disablement disappears on restart. |
| `sentientos/control_plane_kernel.py` (`ControlPlaneKernel.admit`, `admit_and_execute`) | Phase-aware broker for callers that explicitly submit a `ControlActionRequest`. It validates shape/phase, delegates selected classes to RuntimeGovernor and optional proof budget, applies federation rules, and deduplicates allowed correlations. | Reads request metadata, lifecycle phase, startup guard, governor results, optional proof budget. Appends decisions to `glow/control_plane/kernel_decisions.jsonl` (configurable) and best-effort pulse events. | Owns admission only for participating callers. `admit_and_execute` never calls its callback after deny/defer/quarantine. A governor exception defers. Decision-log failure does **not** revoke an otherwise allowed decision. Dedupe is process-local TTL state and is lost on restart; JSONL decisions persist. |
| `sentientos/runtime_governor.py` (`RuntimeGovernor.admit_action`) | Deterministic resource/posture arbiter underneath the kernel for mapped action classes: repair, restart, federation, control-plane task, amendment, and local-model inference. It is also callable directly. | Reads policy mode, pressure, audit trust, federation/trust epoch and selected runtime feedback. Writes pressure, decisions, observability, budgets and rollups beneath `SENTIENTOS_GOVERNOR_ROOT`. | Narrows admission in enforce mode through budgets, quarantine, pressure, trust and arbitration. It neither validates operator grants nor executes effects. Unknown action types are allowed outside enforce mode and denied in enforce mode. Process counters/quarantine reset; files survive restart but are chiefly evidence/rollup, not complete restored counters. |
| `sentientos/governed_local_model_invocation.py` (`GovernedLocalModelInvoker.invoke`) | Canonical bounded local inference entry used by chat/Genesis/commissioned serving. | Requires a valid authority map, eligible exact record/identity, purpose, artifact digest, budgets and correlation; then requests `LOCAL_MODEL_INFERENCE` admission. Writes request, decision and digest-bound receipt JSON. | Kernel denial prevents generation. Backend timeout/failure degrades with a receipt. Output effects are explicitly false for provider network, tools, memory, action, adoption and repository mutation. Receipt persistence occurs after generation and a persistence error is not transactional rollback. |
| `api/actuator.py` (`act`, `run_shell`, `http_fetch`, `file_write`, `send_email`) | General actuator dispatch for shell, HTTP, sandbox file, email and webhook effects. | Reads allowlists/templates, sandbox root, SMTP configuration and process privilege. Writes autonomous logs/reflections plus the external effect. | Final gates are allowlist/path validation plus `require_admin_banner()` and deprecated `require_lumos_approval()` (automatic covenant alignment). It does **not** consult CapabilityRegistry, ControlPlaneKernel, RuntimeGovernor, or local-authorization grants. Missing allowlist/config/privilege fails closed; log persistence is after dispatch and is not an atomic prerequisite. |
| `sentientos/local_diagnostic_effect.py` (`perform_local_diagnostic_effect`) | Explicit bounded artifact writer called by diagnostic-effect wing/build tooling. | Validates a request, output containment, overwrite posture and payload digest; writes temp file, fsyncs and replaces, then constructs result/receipt/postcondition records. | The request is the local admission rule; no kernel/governor/operator grant is consulted in this function. Validation blocks, but mkdir/write/replace failures propagate. A returned result proves the write call completed; later readback proves postcondition. |
| `sentientos/workspace_change_set_execution.py` (`execute_workspace_change_set`) | Multi-target repository/workspace mutation orchestrator over the workspace-file effect wing. | Requires valid request, passed preflight, ready transaction plan and unchanged preflight digests. Emits per-target effect/postcondition/rollback/audit records and aggregate execution results. | Deterministic AND composition, but no kernel/governor call at this boundary. It stops after first failure by policy and can truthfully report partial mutation. Evidence is returned; caller-selected output persistence is separate. |
| `sentientos/local_authorization_grant.py` | Builds digest-bound operator + policy approval evidence, scoped/expiring/revocable grants, verification, expiry and ledgers. Host runtimes consume it as review/custody metadata. | Supplied evidence and explicit timestamps in; immutable records/ledgers out. | The module repeatedly marks these artifacts metadata-only and non-executing. A grant is necessary evidence on the host-fulfillment review chain but is not sufficient effect authority and is not consumed by `api.actuator`. |
| `sentientos/real_effect_admission.py`, `host_real_effect_admission_runtime.py`, and `real_executor_execution_authorization_gate.py` | Planning/review records for future real executors. | Consume closure/evidence artifacts and emit deterministic records. | Explicitly no backend loading, invocation, execution or host mutation. “Ready” is not an executable permit. |

## Actual chains and boolean composition

There are multiple chains rather than one mandatory spine:

1. **Governed local inference:** caller **AND** valid authority-map/record/identity **AND**
   supported purpose **AND** input/resource budgets **AND** correlation budget **AND**
   `ControlPlaneKernel(ALLOW)` **AND**, because inference is mapped, a
   `RuntimeGovernor` allow -> model object's `generate[_governed]` -> invocation receipt.
   Producing text confers no downstream effect flag.
2. **Kernel-mediated maintenance/control actions:** typed request **AND** matching phase
   **AND** startup mediation where applicable **AND** mapped governor allow **AND**
   proof-budget admissibility when supplied **AND** authority-specific checks ->
   callback only when the caller uses `admit_and_execute`. A caller using `admit` must
   itself honor the returned decision.
3. **Host authorization review chain:** readiness evidence **AND** separate operator
   approval **AND** policy approval **AND** issuance admission -> scoped expiring
   revocable grant metadata -> consumption/readiness/admission records. The current
   “real backend” and “real backend invocation” capabilities are deferred; this chain
   terminates before a general host actuator.
4. **Bounded workspace mutation:** valid execution request **AND** passed preflight **AND**
   ready transaction plan **AND** current digest equality -> workspace-file runner ->
   write -> postcondition/rollback/audit records. It is a separate deterministic chain.
5. **General actuator:** normalized intent **AND** type-specific allowlist/path policy
   **AND** administrator privilege **AND** automatic covenant alignment -> concrete
   subprocess/socket/file/SMTP effect -> result, then autonomous/reflection logging.
   Capability admission, kernel, governor and explicit operator-grant artifacts are not
   predicates here.
6. **Legacy/direct utilities and daemons:** module-specific configuration or caller
   invocation -> direct `subprocess`, socket, HTTP, or filesystem call. These paths do
   not share a repository-wide admission predicate.

An operator grant is therefore one input among several on the host review chain, but
process administrator status is effectively sufficient for the privilege portion of
the general actuator after its type policy passes. Neither form universally authorizes
all effects.

## Authority-chain table

| Effect class | Initiator | Capability / operator requirement | Kernel / governor role | Admission owner -> actuator | Receipt/evidence | Failure posture | Confidence |
|---|---|---|---|---|---|---|---|
| Governed local inference | Chat, Genesis advice, serving controller | Eligible exact local authority record; no external-provider credential | Kernel required; governor handles `local_model_inference` | Invoker -> configured local model object | Request/decision/receipt JSON; digest and effect flags | Fail closed before generation; bounded fallback after model failure | High |
| Host real executor | Review/build scripts | Registry says backend and invocation deferred; operator/policy artifacts are metadata only | Review stages may use kernel proposal admission; no live executor | None implemented | Planning/readiness/admission records only | Fail closed by absence of an actuator | High |
| Workspace/repository file mutation | Explicit orchestration caller | Preflight/transaction/digest predicates; no CapabilityRegistry lookup or explicit operator grant in final function | None at final boundary | change-set executor -> workspace-file effect writer | Effect, postcondition, rollback plan, production audit; aggregate can be partial | Fail closed pre-write; fail-stop/partial after earlier writes | High |
| Diagnostic file write | Explicit wing/build caller | Valid contained request; no operator grant | None | diagnostic function -> temp/fsync/replace | Result then receipt and optional readback | Fail closed on validation; exception on actuator/persistence failure | High |
| Actuator shell | API/worker/direct caller | shell argv allowlist + admin; covenant alignment is automatic | None | `run_shell` -> `subprocess.run(shell=False)` | Returned exit/stdout/stderr; later autonomous log | Fail closed on policy/privilege; execution failure surfaced; evidence write not atomic | High |
| Actuator HTTP/webhook | API/worker/direct caller | URL/origin/path allowlist + admin; credentials are merely headers/config | None | `http_fetch` -> resolved direct HTTP(S) transaction | Returned status/text; later autonomous log | Fail closed on malformed/disallowed destination; network errors surface | High |
| Actuator email | API/worker/direct caller | SMTP endpoint + recipient policy + admin; credentials optional/config-dependent | None | `send_email` -> SMTP | Returned recipient; later autonomous log | Missing config/policy fails closed; transport failure surfaces | High |
| Actuator sandbox file | API/worker/direct caller | bounded relative path + descriptor custody + admin | None | `file_write` -> descriptor-relative OS write | Returned path; later autonomous log | Fail closed on escape/symlink/platform limits | High |
| Daemon restart/repair | Healer paths when wired through kernel; separate watchdogs also exist | Kernel path has typed request; watchdog paths use local config | Kernel/governor on healer path; none on direct watchdog subprocess | Path-specific -> restart callback or subprocess | Kernel/governor JSONL on governed path; utility-specific logs elsewhere | Mixed; direct alternates bypass canonical broker | Medium-high |
| Provider/API model call | `model_bridge.py` compatibility provider selection | Environment provider + credential/token; no capability/kernel predicate | None | provider closure -> OpenAI SDK or Hugging Face HTTP | model bridge log, transport exception | Missing SDK/key may fail, but possession/configuration can reach transport directly | High |
| User-visible notification/device/network bridges | Explicit scripts/daemons | Module-specific config, sometimes privilege import | Generally none | direct socket/HTTP/process API | Module-specific or absent | Mixed/unknown by module | Medium |
| Runtime/process replacement | Maintenance resident-adoption workflow or direct launcher/updater | Workflow-specific sealed authority for maintenance path; updater is operator utility | Not a universal kernel predicate | adoption controller -> `os.execve`, or utility -> subprocess | Workflow custody artifacts or utility return code | Governed maintenance path fails closed; direct utilities are separate | High |

## Capability truth

A capability is a `CapabilityRecord`: identifier, category, implementation status,
authority level, source/proof references, implemented/deferred surfaces, forbidden
implications, and requirement flags. The default registry is defined in source; callers
can construct or replace immutable records and explicit evidence adapters derive a new
registry. Status values are `implemented`, `partial`, `scaffolded`, `deferred`,
`blocked`, and `unknown`. Authority levels range from `none` and observation/review
labels to narrowly bounded effect labels.

The registry has no durable canonical mutable admission state. Serialized snapshots may
be persisted by callers; the legacy disable map is in-memory. Concrete consumers use it
for review/proof/dashboard descriptions, not as a mandatory interceptor. Consequently:

* registered does not mean permitted;
* implemented does not mean currently admitted;
* an admission-planning record does not authorize execution;
* runtime phase, policy, environment, exact evidence, pressure, grants, credentials,
  allowlists, and actuator availability can narrow a described capability; and
* direct effect code can operate without consulting registry status.

## ControlPlaneKernel versus RuntimeGovernor

The kernel owns typed, phase-aware orchestration and the final `ALLOW/DENY/DEFER/
QUARANTINE` decision for requests presented to it. It records every such decision,
applies startup and correlation rules, invokes delegates, and optionally couples an
allowed decision to a callback. If it says no, `admit_and_execute` performs nothing;
well-behaved manual callers also stop. General actuator calls, bounded effect writers,
many daemons, network bridges, developer tools and legacy utilities can happen without
consulting it.

RuntimeGovernor is a narrower operational admissibility delegate. It evaluates pressure,
rate/storm budgets, contention/fairness, quarantine, audit trust, federation/trust epoch,
runtime feedback and configured enforce/audit posture. It does not know CapabilityRecord
truth, validate explicit operator grants, or perform effects. The kernel normally
precedes it and incorporates its decision; direct callers can also use it independently.
Governor unavailability/error defers mapped kernel requests. Unmapped kernel authority
classes skip it.

## Model/advisory authority

| Question | Answer and implementation path |
|---|---|
| Grant/change a capability | **No** on the governed path. Model output is text/structured advice; registry updates are deterministic Python calls. |
| Satisfy kernel/governor admission | **Bounded/indirect only** as request metadata/evidence. Deterministic validation and delegates decide; text is not an allow token. |
| Authorize host/network/subprocess/repository/provider effects | **No** through `GovernedLocalModelInvoker`; receipts assert those effects false. **Unknown/unsafe composition is possible** if an external caller deliberately feeds arbitrary model text into a legacy direct-effect API; no repository-wide information-flow guard prevents that composition. |
| Authorize runtime adoption | **No** on the governed path. Maintenance adoption validates separately sealed deterministic authority/custody. |

Legacy memory, perception and presence data can influence proposals or metadata, but none
is read as an authority predicate by the kernel, governor, governed invoker, actuator,
diagnostic writer or workspace execution function inventoried here. Their weak freshness
therefore cannot by itself satisfy these predicates. This is prevention by non-consumption,
not proof that every legacy script is information-flow isolated.

## Network/provider and credentials

Provider configured, provider authorized, network allowed, and request executed are not
synonyms. The governed local invoker rejects provider-like authority and records provider
network false. In contrast, compatibility `model_bridge.py` selects OpenAI/Hugging Face
from environment configuration and directly invokes the SDK/HTTP closure without kernel,
governor, or capability admission. Thus credentials alone are not sufficient in the
general actuator (destination policy and privilege still apply), but credentials plus
provider selection are enough to reach a compatibility provider transport attempt.
Transport availability still determines whether an effect actually succeeds.

Direct network modules include relay/bridge/watchdog/dashboard/federation utilities and
daemons using `requests`, `urllib`, or sockets. Their configuration, authentication and
receipts are module-specific; they do not all route through `api.actuator.http_fetch`.

## Bypass hunt and alternate runtimes

Static searches found direct effects in, among others, `replay.py` (`shell=True`),
`bridge_watchdog.py` and `relay_watchdog.py` (HTTP plus restart subprocess),
`updater.py` (Git mutation/restart), `daemon/codex_daemon.py` (Codex and Git subprocesses),
`daemon/log_federation_daemon.py` (`rsync`), `sentientos/lab/wan_federation.py` (SSH/local
processes), `relay_app.py` (HTTP), `model_bridge.py` (provider calls), runtime service/shell
modules (`Popen`), and numerous operator/developer validation tools. These are bypasses
of the **kernel/governor chain**, not necessarily bugs: some are explicit operator tools,
test/lab infrastructure, launchers, compatibility surfaces, or bounded developer
workflow. Several live daemon/compatibility paths are genuine alternate authority
systems in the narrow sense that their own configuration controls an effect.

WDM/Mesh/relay/federation evidence does not itself grant canonical authority. Federation
control submitted to the kernel is governed; relay/network servers can nevertheless
persist or transmit through their own authenticated/configured paths. Alternate runtime
labels therefore cannot silently mutate capability truth, but alternate code can perform
the concrete effects it already implements without becoming a ControlPlane client.

Follow-up candidate (not repaired here): inventory and classify every production entry
point, then decide explicitly which should migrate behind a shared gate. Do not infer
that merely adding a kernel call would supply operator consent, transactional receipts,
or postcondition proof.

## Evidence, durability, and fail-closed matrix

Kernel/governor decision JSONL proves a decision was emitted, not that a later callback
occurred. Local-model receipts prove a backend call returned/failed and digest its output.
Diagnostic/workspace effect receipts plus readback postconditions are stronger occurrence
evidence. General actuator results/logs are not a transaction: an effect may happen before
reflection/log persistence fails. Review/readiness/admission records prove neither
execution nor occurrence.

| Condition | Current behavior |
|---|---|
| Unknown/disabled capability | Registry validation/diagnostic state reflects it, but direct actuators do not consult it: **fail open relative to capability registry**. |
| Missing operator grant | Host review chain blocks; general actuator instead checks OS admin: **mixed**. |
| Missing policy/allowlist | Actuator destination/command rejects; governor resolved policy determines mode: **fail closed or configured audit-mode allow**, path-specific. |
| Kernel unavailable | Participating construction/import/call fails or mapped delegate error defers; nonparticipants continue: **mixed**. |
| Governor unavailable/error | Mapped kernel request defers; unmapped and non-kernel paths continue: **bounded fail closed**. |
| Malformed evidence | Governed model/grant/workspace chains reject: **fail closed**. |
| Missing credential | Provider/SMTP usually fails before or during transport; unauthenticated configured endpoints may still work: **bounded degradation/path-specific**. |
| Network/model unavailable | Exception/timeout or truthful fallback in governed chat: **bounded degradation**. |
| Actuator failure | Exception or failed return; workspace may be partial: **fail-stop, not atomic globally**. |
| Receipt persistence failure | Kernel still returns its original decision after JSONL failure and pulses best-effort; model persistence can raise after inference; actuator logs are after effect: **not uniformly fail closed**. |
| Weak/stale memory/perception | Not consumed by inventoried admission predicates: **cannot directly grant authority**. |

## Direct answers

1. **Exact chain:** there is no universal one. Each row in the authority-chain table is
   the exact present chain; only participating sensitive actions share kernel/governor.
2. **Capability admission meaning:** registry “admission” entries describe bounded
   implemented/planned posture. Runtime admission is a separate decision.
3. **Admission alone authorizes execution?** No. Evidence, phase/policy, actuator and
   path-specific predicates remain; many “admission” artifacts expressly forbid execution.
4. **Kernel versus governor:** kernel is typed phase-aware broker/decision recorder;
   governor is its operational pressure/trust/budget delegate.
5. **Final boundary:** the concrete OS/library call—`subprocess.run/Popen`, descriptor
   write/replace, socket/HTTP/SMTP transaction, model `generate`, or `os.execve`.
6. **Model direct authority:** no on governed paths; the repository lacks a universal
   taint guard against a caller composing model text with a legacy actuator.
7. **Weak evidence:** not in the traced predicates, so it cannot directly satisfy them.
8. **Credentials:** not universally; compatibility providers can attempt transport from
   configuration+credentials without canonical admission.
9. **Alternate runtimes:** they cannot rewrite canonical capability truth merely by
   evidence, but existing relay/lab/daemon code has separate bounded direct effects.
10. **Fail closed:** governed inference, typed kernel callback, host review, actuator
    allowlist/path checks and workspace preflight do; receipt durability and nonparticipants
    are not globally fail closed.
11. **Bypasses:** yes—numerous direct subprocess/network/filesystem paths, classified above.
12. **Hypothesis:** supported as a design/property of governed cognition paths, disproved
    as an enforcement claim covering the entire present repository.

## Locally evidenced history

Local Git history first exposes the current transitions rather than a trustworthy origin
story: `ControlPlaneKernel` and `RuntimeGovernor` predate the current model-production
series; the series from `857f89b` through `bbaa88d` added catalog authorization,
artifact acquisition, commissioning, activation, serving and governed inference; later
maintenance commits (`80ffc87` onward) added lease/continuity/adoption custody. The
older actuator, bridge, watchdog, updater and daemon families remain parallel surfaces.
These hashes are locally evidenced transition points only, not claims of first creation.

## Reproduction searches

The inventory was checked with targeted `rg` searches for `ControlPlaneKernel`,
`RuntimeGovernor`, capability symbols, and direct `subprocess`, `os.exec*`, socket,
HTTP-client and filesystem mutation calls, followed by source inspection and local
`git log -- <paths>`. The companion test binds only current path/symbol existence,
deterministic serialization and absence of Python runtime consumers; it intentionally
does not turn historical observations into runtime invariants.
