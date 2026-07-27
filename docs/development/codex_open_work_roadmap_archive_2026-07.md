# Codex Open-Work Roadmap Index

This compact index is the current docs-only pointer for safe non-sandboxed work selection. It is intended to keep future Codex prompts short, prevent repeated architecture rediscovery, and reduce mechanical rung drift. It is not an implementation plan for any blocked surface.

## Current sealed or paused areas

- `sandboxed_live_memory_commit_adapter_envelope` is terminal for the sandboxed adapter branch.
- No post-envelope implementation is authorized from that terminal envelope.
- Do not create a sandboxed readiness gate, readiness packet, readiness envelope, or repeated sandboxed gate/packet/envelope/readiness ladder.
- Future continuation requires a separate complete topology decision that names the exact topology, non-recursive handoff, authority boundary, and why existing real-root/final-review/readiness surfaces are insufficient.

## Recently completed safe validation work

- Phase 97-103 context-hygiene denial-phase coverage is wired into the capability registry, default work-item review packet matrix, validation lane contract, and related tests after PR #1866.
- Treat that wiring as current upstream validation coverage, not as authority to add provider invocation, prompt export, external disclosure, runtime execution, or live-memory mutation.

## Recently completed audit/doctrine sweep

These tracks are consumed as of the local history through PR #1872 and should not be selected again as fresh next work without a new gap, fresh operator target, or separate planning pass:

- PR #1868 sealed Codex failure taxonomy, prompt compression, and landing evidence recovery doctrine so future prompts can use compact task-specific deltas instead of duplicated giant prompts.
- PR #1869 sealed work-item attestation matrix proof consistency as review evidence only, without runtime adoption, live work-item mutation, or proof-bundle effects.
- PR #1870 sealed workspace change-set preflight proof coverage as non-mutating validation/review coverage, without admission execution, runtime apply, or closure helper side effects.
- PR #1871 sealed context-hygiene denial-phase documentation consolidation for Phase 97-103 validation coverage, without prompt assembly, prompt export, provider invocation, external disclosure, or runtime authority.
- PR #1872 sealed host-boundary deferred/blocked label audit so remote smoke/probe labels remain optional, read-only, non-default review evidence and never authorize host actuation or fan/PWM/thermal writes.

## Recent consumed storage/operator consent and bootstrap-contract work

These tracks are consumed as of the local history through PR #1922. They record review metadata, verifier contracts, process hardening, and repository-mutation custody only. They must not be reopened as fresh implementation tracks, repeated consent-ladder rungs, or runtime authority surfaces without a separate operator-selected task and an explicit authority contract.

| Consumed track | Sealed by | Current posture | Why consumed | Must not be reopened as | Still-forbidden escalation |
| --- | --- | --- | --- | --- | --- |
| Codex workcell storage policy contract and verifier | PR #1898 and PR #1899 | Storage-policy wording and verifier coverage are review evidence for planned storage behavior. | The policy contract and verifier landed as a pair and are represented in recent history. | A new storage policy rung, live storage admission gate, or storage policy truth source. | Must not authorize storage writes, live-memory mutation, ledger writes, runtime policy enforcement, provider invocation, network calls, or external disclosure. |
| Storage transaction dry-run planner and verifier | PR #1900 and PR #1901 | Dry-run transaction planning remains deterministic metadata for review. | The planner and transaction-plan verifier landed as the bounded dry-run sequence. | A runtime transaction executor, admission path, write path, scheduler, daemon action, or live storage mutation flow. | Must not execute actions, mutate live memory, write ledgers, create glow archives, invoke providers, make network calls, or perform host action. |
| Storage execution readiness dossier and verifier | PR #1902 and PR #1903 | Execution-readiness evidence is a dossier/verifier surface for reviewers only. | The dossier and verifier landed and no fresh readiness implementation gap is opened here. | A runtime readiness gate, readiness packet, readiness envelope, executor grant, or action launcher. | Must not grant runtime authority, executor authority, live-memory mutation, daemon behavior, scheduler behavior, provider invocation, prompt export, network calls, or federation authority. |
| Storage runtime-authority boundary contract and verifier | PR #1904 and PR #1905 | Runtime-authority boundary language is a negative/containment contract and verifier surface. | The boundary contract and verifier landed and already record what evidence cannot do. | A runtime-authority implementation, consent truth source, root admission path, or policy-enforcement daemon. | Must not authorize runtime behavior, host action, ledger writes, glow archives, live-memory mutation, model training, provider calls, prompt export, or federation behavior. |
| Storage operator consent request contract and verifier | PR #1906 and PR #1907 | Consent-request evidence is metadata for operator review and does not prove consent. | The request contract and verifier landed as the bounded request-definition pair. | A consent-ladder advancement, live operator-consent capture system, prompt assembler path, or disclosure mechanism. | Must not grant consent, policy truth, prompt assembly, prompt export, provider invocation, network calls, external disclosure, live-memory mutation, or ledger writes. |
| Storage operator consent request packet and verifier | PR #1908 and PR #1909 | Request packets remain review packets only. | The packet contract and packet verifier landed as a complete metadata pair. | A runtime packet consumer, readiness packet, consent submission channel, or execution packet. | Must not authorize runtime, live-memory mutation, provider invocation, network calls, host action, scheduler behavior, daemon behavior, or federation authority. |
| Storage operator consent response artifact and verifier | PR #1910 and PR #1911 | Response artifacts are review evidence and not operator approval. | The response contract and verifier landed as the bounded response-artifact pair. | A live consent recorder, policy truth source, runtime response consumer, or ledgered approval. | Must not grant consent truth, ledger writes, glow archives, live-memory mutation, provider invocation, prompt export, network calls, host action, or runtime authority. |
| Storage operator consent evidence dossier and verifier | PR #1912 and PR #1913 | Evidence dossiers remain consolidated reviewer evidence only. | The dossier and verifier landed and consumed the evidence-consolidation step. | Another evidence dossier rung, readiness envelope, live consent dossier, or implementation authority bundle. | Must not authorize runtime behavior, live-memory mutation, ledger writes, glow archives, external disclosure, provider invocation, model training, daemon action, or federation behavior. |
| Presentation boundary contract | PR #1914 | The presentation boundary records how storage/operator consent request material may be shown for review without creating action authority. | The boundary contract landed and defines the presentation limit. | A UI/runtime implementation, operator approval path, prompt export, provider prompt, disclosure channel, or live presentation daemon. | Must not authorize runtime presentation, prompt assembly, prompt export, provider invocation, network calls, external disclosure, live-memory mutation, ledger writes, glow archives, host action, scheduler behavior, model training, or federation authority. |
| Presentation verifier initial landing | PR #1915 | The verifier checks presentation-boundary artifacts as metadata-only review evidence. | The initial verifier landed and provides the first bounded validation surface. | A runtime presentation checker, consent capture gate, provider-call preflight, or live display authority. | Must not authorize runtime, provider invocation, network calls, prompt export, host action, live-memory mutation, ledger writes, glow archives, daemon action, scheduler behavior, model training, or federation authority. |
| Presentation verifier output-contract hardening | PR #1916 | The verifier output contract is hardened for deterministic reviewer interpretation. | The output hardening landed and consumed the repair/process-hardening step for this verifier. | A new verifier rung, runtime gate, status truth source, or live presentation authority. | Must not authorize runtime, live-memory mutation, provider invocation, network calls, prompt export, host action, ledger writes, glow archives, scheduler behavior, daemon action, model training, or federation authority. |
| Bootstrap invocation argument contract | PR #1917 | Bootstrap process hardening is documented in [`codex_bootstrap_invocation_contract.md`](codex_bootstrap_invocation_contract.md) and constrains future prompts to supported flags. | The invocation contract landed and consumed the repair for unsupported bootstrap arguments. | A bootstrap bypass, alternate unsupported flag scheme, implementation contract from failed argument parsing, or scaffold authority after nonzero parser exit. | Must not bypass bootstrap, finalizer, matrix, supervisor, PR metadata guard, clean-tree rules, or authority boundaries; must not use bootstrap artifacts to authorize runtime, live-memory mutation, provider invocation, network calls, prompt export, host action, ledger writes, glow archives, daemon behavior, scheduler behavior, model training, or federation authority. |
| Open-work roadmap refresh | PR #1918 | The roadmap was refreshed after the consent, storage, and bootstrap landings. | The refresh recorded already-landed work as consumed metadata and left future work selection to separate operator prompts. | Another roadmap freshness refresh that reopens consent/storage/bootstrap landings, or a replacement implementation plan. | Must not authorize runtime behavior, live-memory mutation, provider invocation, network calls, prompt export, host action, ledger writes, glow archives, daemon behavior, scheduler behavior, model training, federation behavior, repository staging, commits, branch mutation, pushes, or PR creation. |
| Current-roadmap freshness verifier consumed implementation | PR #1919 | The current-roadmap freshness verifier is already implemented as deterministic metadata-only review/test tooling. | The verifier landed and now checks roadmap freshness without selecting or implementing future work. | Another roadmap freshness verifier implementation, runtime gate, readiness gate, status truth source, or implementation selector. | Must not authorize implementation selection, runtime proposal adoption, evidence-to-authority escalation, autonomous repository staging, commits, branch mutation, pushes, PR creation, or repository authority. |
| Autonomous-maintenance repository mutation custody handoff | PR #1920 | Repository mutation custody is sealed by replacing daemon mutation with an external Codex/operator review handoff. | The handoff landed as metadata/review evidence and removed autonomous daemon repository mutation as a path. | Another repository-mutation handoff rung, autonomous repository staging, commit, branch, push, or PR authority, or a runtime proposal adoption path. | Must not grant repository authority, runtime proposal adoption, evidence-to-authority escalation, daemon Git behavior, live-memory mutation, provider invocation, network calls, host action, ledger writes, glow archives, scheduler behavior, model training, or federation behavior. |
| Repository mutation custody v2 digest/revision hardening | PR #1921 | Custody is hardened with v2 approval-time digest and revision binding, external handoff storage, immutable payload verification, and removal of unused daemon-facing mutation helpers. | The digest/revision hardening landed and consumed the custody-hardening rung while keeping handoff readiness non-authority. | Another repository-mutation handoff rung, daemon-facing mutation helper, runtime proposal adoption path, or autonomous Git authority. | Handoff readiness remains non-authority and must not authorize staging, committing, branch mutation, pushing, PR creation, runtime proposal adoption, or repository authority; external Codex/operator landing controls remain required. |
| Repository mutation custody canonical invariants | PR #1922 | Custody is sealed through canonical path/digest invariants, semantic readiness verification, canonical-duplicate contradictions, and ledger-or-approval selection. | The canonical invariant work landed and consumed repository-mutation custody through PR #1922 as review evidence only. | Another repository-mutation handoff rung, runtime proposal adoption path, evidence-to-authority escalation, autonomous repository staging, commit, branch, push, or PR authority. | Handoff readiness and roadmap verification are metadata/review evidence only; they must not authorize autonomous repository mutation, staging, committing, branch mutation, pushing, PR creation, runtime proposal adoption, or repository authority, and external Codex/operator landing controls remain required. |

Verifier/status/presentation/request/response/storage-policy/runtime-authority/handoff-readiness/roadmap-verification evidence in these consumed tracks is metadata and review evidence only. It is not consent, policy truth, operator approval, runtime admission, live-memory mutation authority, provider invocation authority, network authority, prompt-export authority, host-action authority, ledger-write authority, glow-archive authority, daemon or scheduler authority, model-training authority, or federation authority unless a future separately authorized runtime gate says so under its own audited contract. The PR #1918 through PR #1922 tracks are consumed and must not be reopened as another roadmap freshness verifier implementation, another repository-mutation handoff rung, autonomous repository staging, commit, branch, push, or PR authority, a runtime proposal adoption path, or evidence-to-authority escalation.

## Consumed candidate tracks

| Consumed track | Sealed by | Current posture | Still-forbidden escalation |
| --- | --- | --- | --- |
| Landing evidence recovery prompt/body repetition reduction | PR #1868 | Use the compact prompt compression rule and canonical PR-body evidence generation; do not reopen as unspent roadmap work. | Must not bypass finalizer, PR metadata guard, matrix, supervisor, audit, clean-tree, recovery law, or authority-boundary requirements. |
| Work-item lifecycle attestation matrix/proof consistency audit | PR #1869 | Treat proof consistency as sealed review evidence coverage unless tests/docs reveal a fresh gap. | Must not create runtime adoption, new authority, live work-item mutation, or proof-bundle effects beyond review evidence. |
| Workspace change-set preflight proof coverage audit | PR #1870 | Treat preflight proof coverage as sealed non-mutating validation/review coverage unless tests/docs reveal a fresh gap. | Must not perform workspace mutation, admission execution, preflight execution side effects, runtime apply, or closure helper invocation. |
| Context-hygiene denial-phase documentation consolidation | PR #1871 | Treat Phase 97-103 denial-phase documentation consolidation as sealed validation-only doctrine. | Must not add new denial-phase behavior, prompt assembly, prompt export, provider invocation, external disclosure, or runtime authority. |
| Host-boundary deferred/blocked host-actuation label audit | PR #1872 | Treat deferred/blocked host labels as sealed non-authority review labels. | Must not add direct host actuation, fan/PWM/thermal writes, executor authority, admission grants, rollback actions, or panic-path behavior. |


## Process-hardening notes

- The current-roadmap freshness verifier is documented in [`codex_open_work_roadmap_freshness_verifier.md`](codex_open_work_roadmap_freshness_verifier.md) as metadata-only review/test evidence; verifier success does not select or implement any future track and grants no runtime, readiness, commit, PR, or implementation authority.

- Bootstrap invocation drift is sealed by [`codex_bootstrap_invocation_contract.md`](codex_bootstrap_invocation_contract.md): future prompts must use only supported bootstrap flags / documented bootstrap flags, must not use unsupported `--existing-module` / `--existing-cli`, and must stop/retry bootstrap when argument parsing exits nonzero.

## Candidate next work tracks

This section lists documentation/review/test-only options for a future operator to select. It does not select or implement any candidate, does not authorize implementation, and does not grant runtime, live-memory mutation, provider invocation, network call, prompt export, host action, ledger write, glow archive, daemon action, scheduler behavior, model training, or federation authority. Each candidate requires separate operator selection, a fresh bounded prompt, successful bootstrap, and the normal finalizer/matrix/supervisor/PR-metadata controls before any landing.

| Candidate option | Scope if separately selected | Non-authority boundary |
| --- | --- | --- |
| Consent-ladder index/readability consolidation | Consolidate links among existing consent/storage contracts, verifiers, and dossiers without adding a new rung. | Documentation/readability-only. Must not create a consent-ladder rung, consent truth source, readiness packet/envelope/gate, runtime consumer, provider call, prompt export, live-memory mutation, or external disclosure. |
| Next-selection packet template | Draft a template for choosing among safe docs/test-only work items without implying implementation authority. | Planning-only. Must require separate operator selection and must not rank or select a track, grant implementation authority, or authorize runtime, host, provider, network, prompt-export, ledger, glow-archive, daemon, scheduler, model-training, live-memory, or federation behavior. |

## Next selection posture

Future next-work selection should require one of:

- a new Deep Research result;
- a fresh operator-named target;
- a newly discovered consistency gap from tests/docs;
- a safe roadmap candidate selected in a separate bounded planning pass.

## Blocked task classes

Do not select these classes from this roadmap:

- Post-envelope sandboxed adapter continuation without a complete topology decision.
- Any sandboxed readiness gate, readiness packet, readiness envelope, or repeated sandboxed ladder.
- Any task that grants runtime, executor, lock, live-memory, root, admission, adapter, host-actuation, external disclosure, or authority behavior.
- Any task that attempts to recover failed readiness-gate workspaces or blocked scaffolds.
- Any task that treats metadata-only, dry-run, sandbox, review-only, readiness, receipt, or proposal evidence as live authority.

## Prompt compression rule

Future "next" prompts should reference this roadmap index and provide only:

- task title;
- selected roadmap candidate or explicit deviation;
- fresh-current/current-doctrine requirement;
- bootstrap command;
- delta-specific files;
- delta-specific validation;
- unique blockers or authority boundaries.

Reference `docs/development/codex_landing_evidence_recovery_rail.md` for failure classes, task classes, same-workspace recovery, local-node-readiness planning, and distributed-proof topology notes. Expand the prompt only when the selected candidate deviates from this index or requires stricter boundaries. No prompt may use this index to override `AGENTS.md`, bootstrap, finalizer, PR metadata guard, matrix, supervisor, audit, clean-tree, or authority-boundary requirements.
