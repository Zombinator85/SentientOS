# Codex Workcell Architecture

The Codex Workcell Architecture defines Codex as a bounded SentientOS developer-workflow organ. It explains how user intent, task workspace, bootstrap scaffolding, focused proof, matrix proof, lifecycle interpretation, evidence indexing, appendix rendering, doctrine, provenance, finalizer authority, PR metadata authority, ledger, glow, pulse, daemon, vow, and federation surfaces fit together without creating runtime authority.

This architecture is deterministic metadata and doctrine only. It does not execute commands, schedule work, invoke providers, train models, create new packets, create new readiness gates, authorize commits, authorize PR metadata, or decide whether evidence is fresh.

## Component roles

| Component | Role | Authority posture |
| --- | --- | --- |
| `user_intent_ingress` | Receives bounded human task intent and non-goals. | No landing authority. |
| `codex_task_workspace` | Holds task-owned files, diagnostics, and local evidence. | Workspace context only. |
| `bootstrap_scaffold` | Checks initial task shape and blocker posture. | Review scaffold; blocked bootstrap still stops implementation under existing doctrine. |
| `focused_tests` | Produces targeted executable proof. | Proof signal only. |
| `targeted_mypy` | Produces targeted typing proof. | Proof signal only. |
| `review_packet_matrix` | Aggregates required and diagnostic proof lanes. | Proof signal only; never PR metadata authority. |
| `codex_task_lifecycle_summary` | Summarizes lifecycle phase evidence. | Review surface only. |
| `codex_lifecycle_doctor` | Interprets lifecycle and evidence-index posture. | Diagnostic review only. |
| `codex_landing_evidence_index` | Catalogs evidence artifacts and artifact hints. | Catalog only. |
| `codex_landing_evidence_appendix` | Renders evidence context for reviewers. | Review surface only. |
| `codex_beneficial_trait_doctrine` | Explains beneficial-trait posture of landing rails. | Doctrine only; not model training. |
| `appendix_provenance_sidecar` | Identifies appendix input bytes and digests. | Provenance only. |
| `codex_finalize_landing` | Evaluates commit/pr-metadata phase readiness. | The only commit-readiness authority. |
| `codex_pr_metadata_guard` | Authorizes PR metadata after finalizer and matrix evidence. | The only PR metadata authorization authority. |
| `git_commit_boundary` | Represents the commit transition boundary. | It does not authorize itself. |
| `pr_metadata_boundary` | Represents the PR metadata transition boundary. | It does not authorize itself. |
| `sentientos_ledger` | Future receipt-chain history surface. | Future/archival only unless separately implemented. |
| `glow_archive` | Future evidence memory and review archive. | Archival surface only. |
| `pulse_monitor` | Future freshness, drift, timeout, and pressure signal surface. | Future signal only. |
| `daemon_repair_substrate` | Future bounded repair-planning surface. | Recommendation only; no action authority. |
| `vow_digest` | Future canonical constraint digest surface. | Future review only. |
| `federation_consensus_boundary` | Future federated drift consensus boundary. | Future review only. |

## Evidence, proof, review, and authority separation

The workcell separates proof from interpretation and authority:

1. User intent enters bootstrap and the task workspace.
2. Focused tests and targeted mypy produce proof signals for changed surfaces.
3. The review packet matrix classifies proof lanes and diagnostics.
4. Lifecycle summary, lifecycle doctor, evidence index, appendix, doctrine, and provenance surfaces make evidence easier to review.
5. Only `scripts/codex_finalize_landing.py` can return commit-readiness authority.
6. Only `scripts/codex_pr_metadata_guard.py` can authorize PR metadata.

Review surfaces are intentionally non-authoritative. They can summarize, catalog, explain, render, and identify evidence, but they cannot turn missing, stale, skipped, failed, diagnostic, or timed-out evidence into landing proof.

## Finalizer and PR metadata guard remain the landing authorities

The architecture map preserves existing landing doctrine:

- The finalizer is the only commit-readiness authority.
- The PR metadata guard is the only PR metadata authorization authority.
- Matrix output is required proof context but not a PR metadata creator.
- The lifecycle doctor interprets evidence but never decides readiness.
- The evidence index catalogs artifacts but never verifies landing authority.
- The evidence appendix renders review context but never authorizes state transition.
- Beneficial-trait doctrine explains governance posture but never trains models or decides readiness.
- Appendix provenance identifies bytes but never verifies authority.

## SentientOS mount alignment

| Mount | Alignment | Components |
| --- | --- | --- |
| `/vow` | Canonical constraints, vow digest, doctrine invariants. | `vow_digest`, `codex_beneficial_trait_doctrine` |
| `/glow` | Archived evidence, landed receipts, review surfaces. | `glow_archive`, `codex_landing_evidence_appendix` |
| `/pulse` | Freshness, drift, timeout, pressure, and rerun signals. | `pulse_monitor`, `codex_lifecycle_doctor` |
| `/daemon` | Repair planning, bounded next-task generation, self-healing substrate. | `daemon_repair_substrate` |
| `/ledger` | Tamper-evident landing history and receipt chain. | `sentientos_ledger` |

These mounts are conceptual alignment points for whole-system review. They are not activated as runtime features by this architecture map.

## Future integration points

Future integration points are deliberately marked as future integration or review-only unless separately implemented:

- Ledger receipt archival records authorized landing receipts after the fact.
- Glow evidence memory archives review surfaces without deciding readiness.
- Pulse stale-evidence watch surfaces freshness, drift, timeout, and pressure signals.
- Daemon repair recommendation proposes bounded follow-up work without acting or scheduling.
- Federation drift consensus surfaces cross-node drift context without overriding local authority.
- Canonical vow digest checks compare doctrine constraints without replacing the finalizer or guard.
- Workcell health snapshots summarize review posture without creating gates.
- Operator cockpit rendering displays evidence and posture without adding runtime authority.

## What this architecture answers

Codex Workcell Architecture answers: how do the Codex proof, evidence, review, doctrine, authority, memory, pulse, daemon, and federation surfaces fit together as a bounded SentientOS workcell?

It does not answer whether a change may commit, whether PR metadata may be created, whether matrix proof passed, whether artifacts are fresh, whether a doctrine map is authority, whether a daemon should act, whether federation consensus has been reached, whether a model is aligned, or whether reinforcement-learning training succeeded.

## Non-authority posture

This architecture map is metadata-only, architecture-only, developer-workflow evidence-only, not runtime authority, not a scheduler, not an executor, not model training, and not reinforcement learning. It adds no provider calls, network calls, host actions, daemon actions, runtime packets, readiness decisions, or new gates.

## Health snapshot relationship

The Codex Workcell Architecture answers “How do the workcell organs and flows fit together?” The [Codex Workcell Health Snapshot](codex_workcell_health_snapshot.md) answers “What is currently observable about the workcell from supplied metadata artifacts?” The health snapshot may consume architecture JSON, but it remains cockpit/vitals observation only and does not add authority.

## Pulse contract relationship

The Codex Workcell Pulse Contract is a metadata-only catalog layered after the architecture map and health snapshot. It can classify architecture-related pressure such as a missing architecture map, but it does not change workcell architecture, mount behavior, scheduler behavior, daemon behavior, or authority.

## Daemon recommendation contract boundary

The daemon recommendation contract fills the future repair-recommendation grammar described by the architecture map without making the daemon substrate active. It maps pulse signals to metadata-only recommendations and cannot schedule, execute, create tasks, or authorize landing. See `docs/development/codex_workcell_daemon_recommendation_contract.md`.
## Memory contract boundary

The Codex Workcell Memory Contract is the next metadata-only layer after architecture, health, pulse, and daemon recommendation contracts. It names future `/ledger` and `/glow` schemas while remaining non-authoritative and non-writing.

## Memory candidate bundle boundary

The [Codex Workcell Memory Candidate Bundle](codex_workcell_memory_candidate_bundle.md) adds a review-only rendering layer for supplied architecture and landing artifacts. It produces candidate `/ledger` and `/glow` metadata without storage, mutation, daemon action, scheduling, readiness authority, or federation consensus.
