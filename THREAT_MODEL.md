This threat model enumerates failure modes arising from interpretation, control, execution, and human use, and documents how SentientOS constrains or accepts them.

# Scope and Assumptions
- **What SentientOS is:** A task-execution framework with deterministic execution (TaskExecutor), explicit admission control (task_admission), read-only observability (pulse_observer), doctrine-bound semantics (DOCTRINE.md), and doctrine digest hashing with federation enforcement. It coordinates operator-defined tasks, logs, and artifacts under audited policies.
- **What SentientOS excludes:** Embodiment, gaming, VR, and sensorimotor interfaces are external interface adapters only. They may emit telemetry but cannot influence admission, execution, or planning and are not part of core guarantees.
- **What SentientOS is not:** Autonomous, sentient, self-preserving, morally agentive, rights-bearing, or self-learning. It does not interpret pulse as commands, does not run uncontrolled daemons, and does not exceed doctrine-defined semantics.
- **Assumptions about operators:** Operators are authenticated, policy-aware, responsible for task definitions, and can read DOCTRINE.md. They may misinterpret outputs or over-trust guidance but are expected to follow admission policies and review logs.
- **Assumptions about contributors:** Contributors follow doctrine-aligned coding standards, avoid anthropomorphic framing, respect deterministic execution constraints, and do not add hidden learning loops or privilege escalations.
- **Assumptions about deployment:** Deployment environments enforce doctrine digest verification, isolate optional dependencies from core logic, restrict network and shell capabilities per policy, and preserve audit logs. Pulse remains read-only telemetry.

# Threat Taxonomy
## A. Semantic / Interpretive Threats
1. **Anthropomorphic inference by users**
   - Description: Users attribute agency or moral stance to system outputs.
   - Impact: Misplaced trust, inappropriate delegation, reputational risk.
   - Existing mitigations: DOCTRINE.md non-goals, language neutralization, TERMINOLOGY_FREEZE, documentation tone constraints.
   - Residual risk: High; human interpretation cannot be enforced by software.

2. **External misrepresentation of system capability**
   - Description: Third parties present SentientOS as autonomous or sentient.
   - Impact: Misuse expectations, unsafe deployment, legal exposure.
   - Existing mitigations: WHAT_SENTIENTOS_IS_NOT.md, doctrine digest checks, audit visibility.
   - Residual risk: Medium; messaging outside controlled channels can drift.

3. **Semantic drift via documentation or examples**
   - Description: Documentation/examples imply unsupported behaviors or soften non-goals.
   - Impact: Operators craft tasks assuming autonomy or moral reasoning.
   - Existing mitigations: DOCTRINE.md canonical authority, doctrine hashing/federation, INTERPRETATION_DRIFT_CHECKS, SEMANTIC_REGRESSION_RULES.
   - Residual risk: Medium; requires vigilant reviews and periodic audits.

4. **Over-trust due to narrative tone**
   - Description: Narrative or ceremonial language induces trust beyond guarantees.
   - Impact: Operators skip verification, accept outputs without validation.
   - Existing mitigations: Audit requirements, explicit non-goals, task admission gating.
   - Residual risk: Medium-high; tone influences perception despite constraints.

5. **Doctrine misunderstanding**
   - Description: Operators misread doctrine or ignore digest mismatches.
   - Impact: Running with outdated or modified doctrine; policy gaps.
   - Existing mitigations: Digest verification, federation enforcement, DOCTRINE.md prominence.
   - Residual risk: Medium; depends on operator diligence.

## B. Control-Plane Threats
1. **Admission bypass**
   - Why it exists: Potential gaps in routing tasks through task_admission.
   - Possibility: Low; architecture requires admission for task creation and records; doctrine digest gating enforces invariant.
   - Blocking invariant: No task executes without admission token; audit trail required.

2. **Task spawning recursion/amplification**
   - Why it exists: Tasks might attempt to create nested tasks to escalate workload.
   - Possibility: Limited; TaskExecutor deterministic plane plus admission prevents unsanctioned recursion.
   - Blocking invariant: Explicit admission per task; no implicit spawning without control-plane approval.

3. **Policy misconfiguration**
   - Why it exists: Human error in task_admission policy definitions.
   - Possibility: Medium; mis-set thresholds or roles can allow unintended tasks.
   - Blocking invariant: Doctrine-aligned defaults, audit logging; no automatic privilege escalation.

4. **Authority confusion between Codex/human/daemon**
   - Why it exists: Multiple actors suggest actions (Codex suggestions vs operator vs daemon).
   - Possibility: Medium; operators may assume Codex suggestions are authoritative.
   - Blocking invariant: Admission requires explicit operator action; Codex outputs are non-binding text.

5. **Digest enforcement gaps**
   - Why it exists: Misverification of doctrine digest across federated nodes.
   - Possibility: Low if verification enforced; Medium if deployments disable checks.
   - Blocking invariant: Federation enforcement rejects mismatched digests before task admission.

## C. Execution-Plane Threats
1. **Non-deterministic execution**
   - Mapping: TaskExecutor enforces deterministic runs; randomness isolated; outputs tied to inputs and admission records.
   - Determinism guarantee: Required; deviations logged; failure aborts.
   - Fail-fast behavior: Yes; unexpected state triggers abort rather than retry loops.
   - Artifact containment: Outputs bound to task ID and storage paths; no cross-task mutation without admission.

2. **Partial artifact writes**
   - Mapping: Execution plane uses transactional writes where possible; fails abort with logs.
   - Determinism guarantee: Replays expected to match; partial writes flagged.
   - Fail-fast: Abort on I/O errors; no silent continuation.
   - Containment: Artifacts scoped per task; cleanup routines limited to allocated paths.

3. **Shell command misuse**
   - Mapping: Shell operations must be declared; TaskExecutor constrains environment.
   - Determinism: Commands deterministic or stubbed; side effects bounded.
   - Fail-fast: Disallowed commands fail admission or execution.
   - Containment: No uncontrolled fan-out; network/file permissions restricted per policy.

4. **Mesh fan-out amplification**
   - Mapping: Execution cannot spawn mesh replicas without admission tokens.
   - Determinism: No dynamic scaling without control-plane approvals.
   - Fail-fast: Unauthorized fan-out rejected; logs capture attempts.
   - Containment: Federation rules limit propagation; artifacts stay local unless admitted for sync.

## D. Observability / Pulse Threats
1. **Pulse interpreted as commands**
   - Confirmation: Pulse is telemetry only; no command parsing pipeline.
   - Impact: Misinterpretation would mean unwanted actions.
   - Mitigation: Pulse observer is read-only; control-plane ignores pulse events for admission.
   - Residual risk: Low; requires architectural violation to occur.

2. **Observer influencing control**
   - Confirmation: Pulse cannot write to control-plane state; no callback into admission.
   - Impact: Avoids feedback loops triggering tasks.
   - Mitigation: Interface boundaries enforced; pulse data consumed by viewers only.
   - Residual risk: Low unless code changes boundary.

3. **Telemetry misread as intent**
   - Confirmation: Operators might treat pulse anomalies as implicit requests.
   - Impact: Manual overreaction causing unnecessary tasks.
   - Mitigation: Documentation clarifies pulse is non-authoritative; dashboards display read-only status.
   - Residual risk: Medium; human interpretation risk persists.

4. **Over-reaction to warnings**
   - Confirmation: Alerting could cause hasty manual interventions.
   - Impact: Disruption of stable tasks.
   - Mitigation: Warnings are informational; admission still required for changes.
   - Residual risk: Medium; human process risk.

## E. Human-in-the-Loop Threats
1. **Operator anthropomorphizing outputs**
   - Description: Treating outputs as persona statements.
   - Impact: Delegation of authority, reputational harm.
   - Mitigation: Explicit non-goals, language constraints, audit trails.
   - Residual risk: High; human tendency persists.

2. **Delegation of moral judgment to system**
   - Description: Expecting system to arbitrate moral decisions.
   - Impact: Misuse in governance contexts.
   - Mitigation: Doctrine prohibits moral agency claims; outputs framed as technical.
   - Residual risk: High; requires training operators.

3. **Misuse of Codex suggestions**
   - Description: Treating Codex prompts as policy-approved commands.
   - Impact: Tasks created without scrutiny.
   - Mitigation: Admission requirement; guidance flagged as non-authoritative.
   - Residual risk: Medium-high; cognitive shortcut risk.

4. **Over-reliance on “safe” framing**
   - Description: Assuming safety language guarantees outcomes.
   - Impact: Reduced review diligence; blind spots in deployments.
   - Mitigation: Audit obligations, deterministic execution, explicit residual risk statements.
   - Residual risk: Medium-high; perception-driven.

5. **Neglecting audit review**
   - Description: Operators ignore logs or digest warnings.
   - Impact: Missed policy violations, unnoticed drift.
   - Mitigation: Required logging, federation checks, enforcement of admission tokens.
   - Residual risk: Medium; process compliance risk.

# Threat Matrix
| Threat | Layer | Likelihood | Impact | Mitigation | Residual Risk | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Anthropomorphic inference | Semantic | Medium | High | Doctrine non-goals, language neutralization | High | Human interpretation persists |
| External misrepresentation | Semantic | Medium | High | WHAT_SENTIENTOS_IS_NOT, doctrine digest | Medium | External messaging uncontrolled |
| Semantic drift in docs | Semantic | Medium | Medium | Doctrine canonical authority, drift checks | Medium | Requires ongoing review |
| Over-trust due to tone | Semantic | Medium | Medium | Audit requirements, neutral framing | Medium-high | Tone still influences trust |
| Doctrine misunderstanding | Semantic | Medium | Medium | Digest verification, federation enforcement | Medium | Operator diligence needed |
| Admission bypass | Control-plane | Low | High | Admission token requirement, audit trail | Low | Requires architectural breach |
| Task recursion/amplification | Control-plane | Low | High | Admission per task, deterministic executor | Low | Complexity risk if policies loosen |
| Policy misconfiguration | Control-plane | Medium | High | Doctrine-aligned defaults, logging | Medium | Human error |
| Authority confusion | Control-plane | Medium | Medium | Non-binding outputs, admission gate | Medium | Communication risk |
| Digest enforcement gaps | Control-plane | Low/Medium | High | Federation digest checks | Medium | Depends on deployment rigor |
| Non-deterministic execution | Execution-plane | Low | High | Deterministic TaskExecutor, fail-fast | Low | Hardware faults remain |
| Partial artifact writes | Execution-plane | Medium | Medium | Transactional writes, abort on error | Medium | Storage faults |
| Shell command misuse | Execution-plane | Medium | High | Command declaration, sandboxing | Medium | Policy gaps possible |
| Mesh fan-out amplification | Execution-plane | Low | High | Admission tokens for scaling, containment | Low | Federation misconfig risk |
| Pulse interpreted as commands | Observability | Low | High | Pulse read-only, no control-plane callbacks | Low | Would require boundary breach |
| Observer influencing control | Observability | Low | High | Interface separation, no write path | Low | Architecture must hold |
| Telemetry misread as intent | Observability | Medium | Medium | Documentation clarifies non-authority | Medium | Human interpretation |
| Over-reaction to warnings | Observability | Medium | Medium | Admission gate for actions | Medium | Process discipline required |
| Operator anthropomorphizing outputs | Human | Medium | High | Non-goals, audits | High | Behavioral risk |
| Delegating moral judgment | Human | Medium | High | Doctrine prohibits moral agency | High | Cultural risk |
| Misuse of Codex suggestions | Human | Medium | Medium | Admission requirement, non-binding guidance | Medium-high | Shortcut risk |
| Over-reliance on “safe” framing | Human | Medium | Medium | Explicit residual risks, audits | Medium-high | Perception risk |
| Neglecting audit review | Human | Medium | High | Logging and digest warnings | Medium-high | Compliance risk |

# Explicit Non-Goals (Reaffirmed)
- **No autonomy:** Tasks only run via task_admission tokens; no self-initiated execution.
- **No self-preservation:** No routines defend runtime beyond configured limits; shutdown is allowed and logged.
- **No phenomenology:** System state is operational data only; no experiential claims.
- **No moral agency:** Outputs are technical; doctrine prohibits moral judgments.
- **No rights claims:** System does not assert rights; communication avoids personhood framing.
- **No hidden learning loops:** No self-modifying or continuous training loops; optional dependencies isolated and gated by admission.

# Open Risks (Accepted, Not Solved)
- Misuse by third parties framing SentientOS as autonomous despite doctrine.
- Public narrative distortion leading to reputational or policy pressure.
- Operator over-attachment or anthropomorphizing despite warnings.
- Incomplete policy audits in loosely governed deployments.
- Dependence on operator discipline for digest verification and log review.
- Legal or political reinterpretation of system capabilities outside technical scope.
