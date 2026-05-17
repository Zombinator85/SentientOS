# Public Technical Overview for Reviewers

Host actuation safety gates are documented in [Host Actuation Safety Gate Wing](host_actuation_safety_gate_wing.md) (`docs/architecture/host_actuation_safety_gate_wing.md`): safety gates are not authorization, hardware allowlists do not grant control, OS backend declarations do not load/invoke backends, panic stop contracts do not execute panic stop, and real actuation remains deferred.
## SentientOS in one paragraph

SentientOS is a deterministic governance-and-audit runtime for operator-directed AI automation. It can remember prior artifacts, retrieve bounded context, reflect on outcomes, propose improvements, rehearse changes, and participate in federation workflows, but authority is never implicit: changes move through explicit custody, policy, audit, immutability, and local-governance gates before adoption.

## Purpose and non-purpose

### What it is
- A control-plane runtime for policy-gated automation (`sentientos/` and `scripts/` surfaces).
- A deterministic workflow system with explicit audit and integrity verification.
- A repository with verification tooling that treats evidence artifacts, state transitions, and governance checks as first-class outputs.

### What it is not
- Not autonomous goal generation or autonomous authority: operators and local policy remain final authority.
- Not forced federation adoption: federation artifacts do not bypass local adoption gates.
- Not provider invocation and not prompt assembly; prompt/provider boundaries are explicitly verified.
- Not remote execution, auto-update, or transport/sync by receipt alone.

## First reviewer path (short path)

1. Read this document.
2. Read the proof-oriented release-readiness index: `docs/architecture/reviewer_release_readiness_index.md`.
3. Read the whole-system trajectory and missing-organs map: `docs/architecture/sentientos_trajectory_and_missing_organs.md`.
4. Inspect control-plane and policy docs:
   - `docs/control_plane_authority_map.md`
   - `docs/STATE_MACHINE_PROPERTIES.md`
   - `docs/RELEASE_READINESS_MODEL.md`
5. Inspect core verification scripts:
   - `scripts/verify_audits.py`
   - `scripts/audit_immutability_verifier.py`
   - `scripts/verify_context_hygiene_prompt_boundaries.py`
6. Inspect representative tests:
   - `tests/test_verify_audits_cli.py`
   - `tests/test_federated_improvement_local_variant_artifact.py`
   - `tests/test_run_tests_bootstrap_airlock.py`
   - `tests/test_phase101_provider_invocation_denial_enforcement.py`
7. Run the proof-map commands in this document and validate output artifacts under `glow/audits/`.
8. Evaluate hard invariants below before considering any runtime or federation claim.

## Core control-plane model

At a high level, SentientOS separates:
- **Admission** (what requests, artifacts, or proposals are accepted for evaluation),
- **Policy and invariants** (what is allowed to proceed),
- **Evidence and audit** (what must be recorded and verified), and
- **Adoption** (what, if anything, becomes locally effective).

This separation is reflected in dedicated verifier scripts, state and readiness docs, and tests that enforce deny-by-default behavior for restricted surfaces. Admission idempotency uses a bounded process-local TTL dedupe cache with inspectable status; it is an availability and duplicate-suppression guard, not durable authority.

## Authority classes (practical reading)

- **Local operator authority:** final decision authority for local node behavior.
- **Policy/invariant authority:** rule surfaces that gate progression (admission, readiness, adoption).
- **Evidence authority (non-execution):** artifacts can prove history/lineage/readiness but do not execute themselves.
- **Federation input authority (bounded):** remote evidence can be received and compared, but cannot force local adoption.

## Audit + immutability spine

The repo includes explicit audit and immutability verification tooling:
- Audit chain verification (`scripts/verify_audits.py`, `scripts/verify_audits`).
- Immutability checks (`scripts/audit_immutability_verifier.py`).
- Corridor checks that compose integrity gates (`scripts/protected_corridor.py`).

The operational posture is fail-closed: unresolved audit/integrity issues are treated as blocking conditions for trusted progression.

## Request/admission lifecycle (reviewer view)

Typical request/proposal flow is:
1. Intake (artifact/request received).
2. Validation and policy checks.
3. Evidence recording (audit trails, manifests, receipts).
4. Readiness/rehearsal evaluation where applicable.
5. Separate adoption decision under local governance.

Important distinction: readiness/rehearsal outputs are support evidence, not automatic execution authority. Recent maintenance forge/merge ticks are also gated through admission, and maintenance tick handling keeps degradation at the top-level boundary instead of allowing unchecked progression.

## Degradation and quarantine behavior

When integrity or policy checks fail, the runtime uses degraded/quarantine handling patterns rather than silently continuing. Reviewers can inspect:
- Quarantine-oriented handling in `scripts/verify_audits.py` and `scripts/apply_audit_repairs.py`.
- Quarantine/degraded tests such as `tests/test_audit_doctor.py`, `tests/test_contract_sentinel.py`, and `tests/test_cathedral_review.py`.

## Memory, context, and reflection loop boundaries

SentientOS contains memory/context and reflection-style surfaces, but with bounded usage and explicit policy checks. Context hygiene and prompt-boundary enforcement are verified by:
- `scripts/verify_context_hygiene_prompt_boundaries.py`
- phase tests such as `tests/test_phase95_provider_invocation_readiness_manifest.py`, `tests/test_phase97_external_security_review_packet.py`, and `tests/test_phase101_provider_invocation_denial_enforcement.py`

Memory/context selection improves retrieval quality; it is not treated as truth authority by itself.

## GenesisForge/Codex self-amendment loop (governed)

Self-amendment/proposal workflows are represented as governed proposal and review components (for example, status/reporting and review/quarantine paths). Review targets include:
- `scripts/forge_status.py`
- `scripts/work_plan_build.py`
- `scripts/work_plan_run.py`
- tests covering amendment interception/quarantine behavior (`tests/test_amendment_sentinel.py`, `tests/test_codex_anomalies.py`, `tests/test_codex_rewrites.py`)

Interpretation boundary: proposal generation, simulation, or repair evidence is not equivalent to local adoption authority.

## Embodiment boundaries

Embodied/adapter telemetry exists as optional integration surface. Public reviewer posture:
- Embodiment integrations are non-core adapters.
- Telemetry is non-authoritative by default.
- Deterministic governance/audit core does not depend on a specific embodiment runtime.

See `docs/EMBODIED_PIPELINE.md` for adapter context while treating control-plane gates as authoritative.

## Federation and local sovereignty model

SentientOS supports sovereign multi-node coordination where evidence may be exchanged and compared. Local node governance remains authoritative for adoption. Federation-specific artifacts and tests should be read as custody and lineage controls, not forced execution channels. Current review coverage includes trust ledger startup recovery with event replay fallback and repaired probe prioritization ordering.

## Federated self-improvement custody runway (metadata-only)

Current runway terms are best interpreted as custody metadata stages:
- **Candidate evidence:** candidate improvement artifacts with supporting proof.
- **Intake receipt:** acknowledgement that evidence entered local review.
- **Custody runway:** tracked progression state for local evaluation.
- **Local variant:** locally materialized evaluation variant for comparison.
- **Lineage comparison:** provenance and divergence assessment.
- **Dissemination receipt:** record that metadata/receipt was cataloged for possible announcement, without transport or sync authority.

These artifacts are **not** transport execution, **not** transport/sync by receipt alone, **not** adoption, **not** merge/apply/install, **not** forced update, **not** provider invocation, **not** prompt assembly, and **not** runtime authority by themselves.

## Model/runtime loading posture

Chat/model runtime coverage now includes lazy chat service model loading and safe defaults for local transformer model code execution. Local transformer loading defaults `trust_remote_code` to false and requires explicit opt-in where remote model code execution is intended.

## Installer and test-runner reliability posture

Reviewer-facing reliability posture:
- Canonical test entrypoint is `python -m scripts.run_tests`.
- Bootstrap/airlock behavior, including the minimal test-airlock bootstrap custody note, is covered by `tests/test_run_tests_bootstrap_airlock.py`.
- Integration pytest marker compatibility is covered by `tests/test_integration_conftest_compat.py`.
- Audit and immutability checks are first-class pre-merge expectations in repository guidance.

## Hard invariants

- Local operator authority is not overridden by federation.
- Remote nodes cannot force adoption.
- Improvement evidence is not execution authority.
- Rehearsal is not adoption.
- Readiness is not adoption.
- Dissemination is not transport execution.
- Embodiment telemetry is non-authoritative by default.
- Memory/context selection is not truth authority.
- Prompt/provider invocation remains gated or blocked according to current phase posture and boundary checks.
- Audit/immutability failures fail closed.

## Translation layer (internal terms -> engineering terms)

- **Cathedral** -> governed runtime / control plane
- **Covenant** -> invariant policy set
- **Ritual** -> auditable workflow
- **Vow** -> immutable or protected commitment artifact
- **Glow** -> audit/provenance output
- **Federation** -> sovereign multi-node coordination
- **GenesisForge** -> governed capability proposal pipeline
- **CodexHealer / SpecAmender** -> repair/amendment workflow components

For broader internal language mapping, see `docs/PUBLIC_LANGUAGE_BRIDGE.md`.

## Recent hardening checks

The current reviewer proof path is summarized in `docs/architecture/reviewer_release_readiness_index.md` and covers these repaired areas:
- Control-plane admission, runtime closure, maintenance admission gating, and degradation boundaries.
- Federation trust ledger startup recovery, event replay fallback, and probe prioritization ordering.
- Chat/model lazy loading and local transformer `trust_remote_code` safe default behavior.
- Integration pytest marker compatibility and minimal test-airlock bootstrap custody.
- Federated improvement custody runway receipts and lineage/dissemination metadata.

## Proof map (commands and tests)

Run from repository root:

```bash
# Control-plane and runtime hardening
python -m scripts.run_tests -q tests/test_control_plane_kernel.py
python -m scripts.run_tests -q tests/test_sentientosd_runtime_closure.py

# Federation trust ledger recovery and probe ordering
python -m scripts.run_tests -q tests/test_trust_ledger.py sentientos/tests/test_trust_ledger_recovery.py

# Chat/model runtime loading and local model safety
python -m scripts.run_tests -q tests/test_chat_service_lazy_loading.py tests/test_local_model.py tests/integration/test_chat_mistral_runtime.py

# Test-runner bootstrap and integration marker compatibility
python -m scripts.run_tests -q tests/test_integration_conftest_compat.py tests/test_run_tests_bootstrap_airlock.py

# Federation improvement custody runway
python -m scripts.run_tests -q tests/test_federated_improvement_candidate.py tests/test_federated_improvement_intake_receipt.py tests/test_federated_improvement_custody_runway.py tests/test_federated_improvement_local_variant_artifact.py tests/test_federated_improvement_lineage_comparison_receipt.py tests/test_federated_improvement_dissemination_receipt.py

# Prompt-boundary verifier
python scripts/verify_context_hygiene_prompt_boundaries.py

# Audit verifier
python scripts/verify_audits.py --strict

# Immutability verifier
python scripts/audit_immutability_verifier.py --manifest vow/immutable_manifest.json

# Docs dependency check and docs build
python scripts/build_docs.py --check-deps
python scripts/build_docs.py
```

## Internal language / cultural layer

Internal and legacy cultural documentation remains available and is not removed by this overview. Reviewers who need term mapping should start with:
- `docs/PUBLIC_LANGUAGE_BRIDGE.md`
- `docs/enter_cathedral.md`
- `AGENTS.md` (repository governance ledger)

## Host embodiment substrate

See `docs/architecture/host_embodiment_substrate_phase1.md` and `docs/architecture/host_embodiment_substrate_phase2_read_only_discovery.md` and `docs/architecture/host_embodiment_substrate_phase3_policy_receipts.md` and `docs/architecture/host_embodiment_substrate_phase4_privilege_broker.md` and `docs/architecture/host_embodiment_substrate_phase5_actuation_fulfillment_scaffold.md` for Host Embodiment Substrate phases 1 through 5.


### Host Embodiment Phase 4 Privilege Broker

See `docs/architecture/host_embodiment_substrate_phase4_privilege_broker.md`. Phase 4 evaluates proposal receipts for future privileged-action eligibility only. Eligibility is not authorization, a broker receipt is not fulfillment, fan/PWM/thermal control remains blocked/deferred, and the future Actuation Fulfillment Layer is still required before any effect can occur.


### Host Embodiment Phase 5 Actuation Fulfillment Scaffold

See `docs/architecture/host_embodiment_substrate_phase5_actuation_fulfillment_scaffold.md`. Phase 5 creates fulfillment rehearsal plans and rehearsal receipts only. Fulfillment rehearsal is not real fulfillment, a rehearsal receipt is not an effect receipt, no host mutation occurs, and fan/PWM/thermal/power/service/cleanup actions remain blocked/deferred behind future control-plane admission, operator/policy approval, audit, rollback, effect receipt, and postcondition gates.


## Host Embodiment Execution Proof Wing

Next proof/readiness wing: `docs/architecture/host_embodiment_execution_proof_wing.md`. Execution readiness is not authorization; the future effect receipt schema is not proof of effect; the Runtime Supervisor does not restart/kill services; real actuation remains deferred.

## Host Embodiment Authorization Review Wing

Next review-only wing: `docs/architecture/host_embodiment_authorization_review_wing.md`. Authorization review is not authorization grant; the future authorization grant schema is not a real grant; real fulfillment remains deferred; real actuation remains deferred. Future cooling, power, service, and cleanup actions remain behind explicit future authorization, control-plane admission, audit, rollback, effect receipt, and postcondition checks.

### Controlled authorization + trace proof

The [Host Embodiment Controlled Authorization + Trace Wing](host_embodiment_controlled_authorization_and_trace_wing.md) adds a contract-only controlled authorization schema and a demo/proof-only host embodiment trace. The controlled authorization contract is not a live grant; the grant record is schema-only/future-use-only; the demo trace is reviewer proof only; real fulfillment and real actuation remain deferred.

Proof path: docs/architecture/host_embodiment_controlled_authorization_and_trace_wing.md

## Host Embodiment Reviewer Demo Trace

See `docs/architecture/host_embodiment_reviewer_demo_trace.md` for the one-command deterministic reviewer trace. Run `python scripts/build_host_embodiment_trace.py --format json`, `python scripts/build_host_embodiment_trace.py --format markdown`, or `python scripts/build_host_embodiment_trace.py --validate-only`. The demo trace is reviewer proof only, no host mutation occurs, PWM presence is not control authority, the controlled authorization contract is not a live grant, and grant/revocation records are schema-only/future-use-only.


Reviewer first-run proof bundle: `docs/architecture/reviewer_first_run_proof_bundle.md`.

Host live-grant readiness is documented in [Host Live-Grant Readiness Wing](host_live_grant_readiness_wing.md) (`docs/architecture/host_live_grant_readiness_wing.md`): live-grant readiness is not a live grant, the operator/policy approval packet is not approval, grant issue preflight does not issue a grant, and real actuation remains deferred.


Local authorization grant records are documented in [Host Local Authorization Grant Wing](host_local_authorization_grant_wing.md) (`docs/architecture/host_local_authorization_grant_wing.md`): a local authorization grant is authority metadata, not fulfillment; grant verification is not fulfillment authorization; real actuation remains deferred.

Reviewer proof link: [Host Fulfillment Authorization Consumption Wing](host_fulfillment_authorization_consumption_wing.md) documents the metadata-only authorization-consumption layer. Consuming authorization is not fulfillment; scope match is not execution; real actuation remains deferred.

Path: `docs/architecture/host_fulfillment_authorization_consumption_wing.md`.

Reviewer map: [Host Fulfillment Executor Contract Wing](host_fulfillment_executor_contract_wing.md) (`docs/architecture/host_fulfillment_executor_contract_wing.md`) follows fulfillment authorization consumption. Executor contract is not an executor; backend declaration does not load/invoke backend; dry-run plan is not dry-run execution; admission packet is not control-plane admission; real actuation remains deferred.


See also: [Host Dry-Run Execution Harness Wing](host_dry_run_execution_harness_wing.md) (`docs/architecture/host_dry_run_execution_harness_wing.md`), which is simulation-only; dry-run execution is not real fulfillment, dry-run result is not an effect receipt, dry-run receipt is not proof of host mutation, and real actuation remains deferred.

See also: [Host Dry-Run Effect Verification / Audit Closure Wing](host_dry_run_audit_closure_wing.md) (`docs/architecture/host_dry_run_audit_closure_wing.md`), which verifies dry-run evidence only; it is not a real effect receipt, not a real host postcondition check, not real rollback, not a production audit receipt, and real actuation remains deferred.


## Real effect capability admission link

See [Host Real Effect Capability Admission Wing](host_real_effect_capability_admission_wing.md) (`docs/architecture/host_real_effect_capability_admission_wing.md`): dry-run closure does not automatically permit real effects; real effect admission is not implementation, the admission decision does not authorize implementation or execution, the plan scaffold does not start implementation, cooling/hardware control remains blocked by default, and real actuation remains deferred.

For the first intentionally real but bounded effect, see the [Host Local Diagnostic Effect Pilot Wing](host_local_diagnostic_effect_pilot_wing.md), which only writes one explicit local diagnostic artifact and is not run by reviewer bundles by default.

Host embodiment proof now includes an explicit [local diagnostic effect pilot](host_local_diagnostic_effect_pilot_wing.md) and matching [exact artifact rollback pilot](host_local_diagnostic_exact_rollback_pilot_wing.md); reviewer bundles document but do not run either by default.

The [Host Local Effect Transaction Ledger Wing](host_local_effect_transaction_ledger_wing.md) (`docs/architecture/host_local_effect_transaction_ledger_wing.md`) adds metadata-only lifecycle integrity for the local diagnostic effect and exact rollback; it adds no new host effect and is not general cleanup or broader host control.

See also: [Host Steward / Delegated Runner Boundary Wing](host_steward_delegated_runner_boundary_wing.md) (`docs/architecture/host_steward_delegated_runner_boundary_wing.md`) for the next authority boundary after the local effect transaction ledger. It models broad top-level host-steward authority without granting delegated runners ambient authority.

- `docs/architecture/host_builtin_local_effect_runner_pilot_wing.md` — first actual delegated runner implementation; in-process only; supports only local diagnostic artifact write and exact-artifact rollback; not a general runner framework; no subprocess/shell/network/provider/prompt.

Related: [Host Built-In Runner Transaction Orchestrator Wing](host_builtin_runner_transaction_orchestrator_wing.md) — bounded orchestration of only the existing built-in diagnostic write, optional exact rollback, and explicit transaction ledger; not a general runner framework.

## Workspace-scoped file update pilot

See [Host Workspace-Scoped File Effect Pilot Wing](host_workspace_file_effect_pilot_wing.md) (`docs/architecture/host_workspace_file_effect_pilot_wing.md`): the next bounded real-effect pilot after the runner transaction orchestrator creates or updates exactly one explicit file inside an explicit workspace root, captures preimage before replacement, verifies postcondition, supports exact-target rollback only, is not general filesystem access, is not cleanup, and does not use subprocess/shell/network/provider/prompt or hardware/service/power/fan/thermal authority.
