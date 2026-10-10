# Repository system atlas — `84c5687c`

> **Snapshot:** `repository-system-atlas:84c5687c841e83187d8017c4b84fd6b038937432`  
> **Bound source commit:** `84c5687c841e83187d8017c4b84fd6b038937432`  
> **Bound source tree:** `20c7a14e8909c63d108c94f07cc088357a16943e`  
> **Posture:** immutable, source-bound, repository-derived, descriptive, and non-authorizing.

This census describes the source tree at the bound commit. Its JSON companion is [`architecture/repository_system_atlas_84c5687c.json`](../../architecture/repository_system_atlas_84c5687c.json). Later commits that select this snapshot or update prose are not part of its source census. The published `main` observed during the census was `197e2a4ceeb13ab59a88fd531283355e15e1fd7d`; it is a separate, older revision. This campaign did not inspect a deployed runtime or establish production behavior.

The prior selected snapshot remains [`b7df2a07`](repository_system_atlas_b7df2a07.md), followed by [`3116672d`](repository_system_atlas_3116672d.md) and the older [historical atlas](current_repository_system_atlas.md). All snapshots remain unchanged. See the [atlas index](system_atlas_index.md) for the complete chain.

## Census and source delta

The bound Git tree has **6,261 tracked paths**: 3,767 Python files, 2,527 paths under `tests/`, 472 under `scripts/`, 791 under `docs/`, 17 under `architecture/`, 683 Markdown files, 1,530 JSON files, and one Rust file. These counts are path inventory, not a measure of working behavior.

The metadata-only capability registry builds **368 records**: 293 implemented, 16 partial, 22 deferred, 36 blocked, and 1 scaffolded. A row's declared status is not evidence that a runtime owner is composed, enabled, executing, or producing an effect. The atlas includes every record, its declared paths, and existence results in the JSON companion.

Compared with the prior selected source commit `b7df2a07…`, 471 tracked paths differ (163 added, 308 modified, none deleted): 42 paths under `sentientos/` (13 added, 29 modified), `sentientosd.py`, 245 test paths, 11 script paths, and 28 documentation paths, among other files. This is a Git path comparison, not a behavioral or production claim. Relevant construction changes include authenticated causal-resource principal and currentness owners, bounded local-model allocation and provisioning, persistent epistemic state, recovery-aware developmental writeback, model-provenance/serving identity attribution, transition recovery, and expanded causal introspection.

## Read the maturity dimensions separately

| Dimension | Meaning in this atlas |
|---|---|
| Implemented mechanism | A source owner, controller, protocol, or bounded persistence mechanism exists. |
| Configured composition | An explicit owner-to-owner path exists when its named configuration or injected owner is supplied. |
| Runtime enablement | Deployment configuration and enable flags are present; source cannot establish that external fact. |
| Independently observed execution | A separate observation shows the named path ran; code and synthetic exercises do not establish it. |
| Production evidence | A qualifying nonsynthetic deployed event and relevant custody exist. This census did not establish such an event. |
| Projected closure | Implementation, composition, operation, independent evidence, or an outcome study remains open. |

No dimension implies another. “Not inspected” remains unknown, not proof of absence or impossibility.

## Resident causal path

The daemon's source-defined tick ordering is:

```text
bounded host/subsystem observation
-> World-State snapshot
-> resident cognition using custody captured before the tick
-> configured epistemic update and self-model reconciliation
-> causal-introspection capture
-> later World-State and later cognition may consume eligible retained evidence
```

The exact owners, inputs, opt-in configuration, temporal gates, and authority limits are recorded per subsystem in the JSON. Important properties include:

- `sentientosd._run_maintenance_tick` runs configured observations before `RuntimeMaintenanceSurfaces.build_world_state_board()` and cognition.
- Epistemic development uses explicit source selectors and proposition/rule configuration. It preserves source time/freshness, uses separate evidence and state admissions, and commits state against an exact predecessor. The next cognition consumes only verified retained prior state.
- Developmental history stores admitted interpretation separately from current World-State and canonical user-retained memory. Cognition runs before the current tick's writeback; recovery reconstructs completed custody without making same-tick records eligible.
- Longitudinal self-model reconciliation and causal-introspection capture follow cognition. Their immutable evidence can become a later-tick input, not a same-tick certification.
- Model and software succession journals keep proposals, stages, effects, activation/adoption, serving, and observed running identities distinguishable. Missing or contradictory identity evidence remains unavailable or degraded.

## Important unresolved bridge: resource consumption into resident evidence

The source contains real bounded pieces:

1. `production_chat_resource_provisioning.py` verifies an installation-scoped, pre-issued principal/allocation bundle and composes a resource context. It does not create an allocation or grant authority.
2. `chat_service.py` can explicitly use that context for resource-backed production inference.
3. The governed invocation owner can send exact receipts to `RuntimeMaintenanceSurfaces.register_governed_invocation_receipt()`, which validates, deduplicates, bounds, and persists receipt evidence.
4. `host_resource_runtime.resource_consumption_world_state_records()` can join receipts to an injected allocation ledger for a read-only World-State projection.

The standard `sentientosd` construction passes its governed local invoker, but does not pass `governed_resource_ledger` to `RuntimeMaintenanceSurfaces`. The chat resource context and daemon projection therefore do **not** currently form one canonical resource-backed resident evidence path. The projection requires an explicit trusted ledger owner; no ambient discovery or synthetic allocation is implied. Host-level CPU/GPU observations are not per-invocation measurements, and unknown consumption remains unknown. This bridge is tracked as unfinished rather than counted as composed.

## Succession, attribution, and recovery

Model-development manifests are verified against preregistered protocol identity and exact model role. `sentientosd` reports provenance as verified only when the bound active model identity matches the referenced subject; a proposal or manifest alone does not identify a running model. Resident serving-session identity, transition-journal stage, and predecessor/successor model identities are separate observations.

Software adoption preserves predecessor and successor generation evidence, exact transition configuration, authority continuity, process-image replacement, readiness, and recovery posture. The source has bounded recovery mechanisms; the atlas does not infer universal crash recovery, a successful live transition, or beneficial consequence. A Git commit is not evidence that the committed generation is running.

## Other major organs

| Surface | Source-backed status | Boundary |
|---|---|---|
| Canonical conversation memory | `CanonicalMemoryStore`, explicit retention admission, and chat retrieval/retention exist. | User-retained canonical memory is distinct from developmental history and epistemic state; no current-truth or action authority follows. |
| Local model supply | Catalog, commissioning, activation, serving, inference, and publication owners exist as separate stages. | A deterministic fake-provider publication path is not sovereign production publication; artifact or activation does not prove a running model. |
| Installation and generation zero | Installation-scoped custody, genesis provisioning, bounded POSIX commissioning, and a startup gate exist. | Provisioning is not a production commissioning event; no such event was established here. |
| Embodiment | Body/fulfillment/observation and consequence machinery exists, with explicit owner injection into World-State. | Renderer claims do not substitute for an independent observer; no physical deployment or observation was examined. |
| Federation | Typed candidates and bounded local lifecycle/transport owners exist. | Receipt, readiness, and remote agreement do not become local authority; default production WAN synchronization is not established. |
| Resident supervision | Scheduler, wake, successor adoption, and bounded parent supervision owners exist. | This is not universal unexpected-death recovery or automatic rollback across every transition. |

The detailed source references for these surfaces are in the JSON crosswalk and were checked against the bound tree. Where configuration or operation depends on external installation state, this census records it as unknown rather than inferring it from source.

## Authority and temporal boundaries

```text
evidence != interpretation != retained history != current truth
resource entitlement != effect authority
proposal != admission != execution != observed effect
artifact / commit != activated model or running software generation
```

Epistemic position, motivational assumptions, and consequential authority remain separate. Runtime admission is narrow and domain-owned; this atlas grants no permission, capability, resource, provider access, or production activation.

## Source references and unknowns

All source paths cited by the system records resolve in the bound tree. All 568 declared capability proof-test paths resolve as tracked paths. The registry also declares one missing source-file reference, `sentientos/embodiment/avatar_state.py`; the affected capability row preserves that mismatch rather than silently treating it as an existing source. Directory references are accepted only when a tracked descendant exists.

This census did not inspect deployment environment values, live owner configuration, runtime journals outside the repository, providers, physical hardware, or external production evidence. It therefore leaves runtime enablement, independent execution, production benefit, actual per-invocation physical resource use, current running model/software identities, native deployment, and external production observations **unknown or not established**.

The full source path map, 368-row registry crosswalk, census methodology, exact commit/tree binding, production boundary, and remaining unknowns are in the [machine-readable atlas](../../architecture/repository_system_atlas_84c5687c.json).
