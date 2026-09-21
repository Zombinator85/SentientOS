# Current Repository System Atlas

> **Posture:** descriptive, repository-derived, non-authority archaeology. This document does not grant, admit, activate, execute, or adopt anything. It records the tree at `c32ff141f110a4542e10801bea682a87ddf20817`. External comparator research was not used.

## 1. Executive summary

SentientOS is a large, multi-era Python repository whose current center is an explicitly governed resident runtime, a hardened local-model service path, domain-specific evidence and custody chains, and an extensive set of operator/developer tools. Source existence, composition, enablement, automatic exercise, effect capability, and authorization are independent facts throughout this atlas.

The default `sentientosd` composition continuously evaluates maintenance evidence, builds World-State material, and composes read-only host review surfaces. It can construct additional maintenance owners only when exact adoption configuration is supplied. It does **not** make every importable cognition, actuator, federation, council, camera, model, or historical daemon resident. The packaged `sentientos-chat` path is the clearest current local-model service composition. External-model HTTPS and host-effect implementations exist, but their existence is not a default grant, credential, admission, or active effect.

The capability registry contains **355** records: blocked=36, deferred=22, implemented=284, partial=11, scaffolded=2. “Implemented” is bounded by each record's implemented surfaces and forbidden implications. The registry is not itself proof of production composition.

### Non-negotiable distinctions

```text
implemented != composed != enabled != automatically exercised
actuator exists != authority exists != admission exists != effect occurred
metadata/proposal/review/receipt != adoption or authoritative current state
synthetic behavioral proof != production composition
model confidence != evidence authority
```

## 2. Repository census

| Measure | Count/value |
|---|---|
| architecture_artifact_count | 4 |
| documentation_path_count | 684 |
| formal_spec_count | 9 |
| package_families | ['sentientos', 'api', 'gui', 'apps'] |
| python_path_count | 3611 |
| runtime_artifact_conventions | ['logs/', 'glow/', 'artifacts/', 'architecture/', 'JSON/JSONL ledgers', 'atomic state files'] |
| script_path_count | 455 |
| test_path_count | 2439 |
| tracked_path_count | 5881 |

The tracked-path census is exhaustive in the JSON family inventory: every tracked path is assigned to exactly one family. Family assignment is organizational and never substitutes for AST/import reachability. Package metadata declares `sentientos`, `api`, `gui`, and `apps`; numerous top-level Python modules remain shipped compatibility surfaces.

## 3. Primary runtime composition

### Resident `sentientosd`

`sentientosd:main` installs signal shutdown and runs `run_loop`. Each tick closes runtime maintenance calls onto concrete signal collection, Forge/Codex handoff, host observation/review, and World-State construction. Maintenance scheduler, wake, successor-generation, authority-continuity, and resident-replacement owners are configuration-selected and fail closed on overlap or failed readiness. The cognitive cycle is not scheduled merely because it is importable.

### Hardened local chat

`sentientos-chat` targets `sentientos.chat_service:run`. Its hardened path consumes installed/commissioned/activated model custody, opaque serving, independent inference admission, and durable conversation identity. Simulation is explicit rather than a fallback. Automatic serving recovery, hot switching, model discovery, and provider fallback remain deferred.

### Operator/developer interfaces

The package exports {len(x['supported_entrypoints'])-7} console scripts plus seven package/module launch forms. Most are one-shot operator tools. Cathedral, ritual, avatar, federation, node, and older UI names remain visible without becoming resident by name.

## 4. Current entrypoints and reachability

| Entrypoint | Target | Kind | Activation |
|---|---|---|---|
| support | support_cli:main | packaged_cli | operator-gated |
| ritual | ritual_cli:main | packaged_cli | operator-gated |
| sentientos-procedure | ritual_cli:main | packaged_cli | operator-gated |
| treasury | treasury_cli:main | packaged_cli | operator-gated |
| avatar-gallery | avatar_gallery_cli:main | packaged_cli | operator-gated |
| avatar-presence | avatar_presence_cli:main | packaged_cli | operator-gated |
| review | review_cli:main | packaged_cli | operator-gated |
| diff-memory | diff_memory_cli:main | packaged_cli | operator-gated |
| theme | theme_cli:main | packaged_cli | operator-gated |
| suggestion | suggestion_cli:main | packaged_cli | operator-gated |
| trust | trust_cli:main | packaged_cli | operator-gated |
| video | video_cli:main | packaged_cli | operator-gated |
| plint-env | scripts.plint_env:main | packaged_cli | operator-gated |
| cathedral-gui | gui.cathedral_gui:main | packaged_cli | operator-gated |
| sentientos-governance-ui | gui.cathedral_gui:main | packaged_cli | operator-gated |
| sentient-api | sentient_api:app.run | packaged_cli | operator-gated |
| sentientosd | sentientosd:main | packaged_cli | operator-gated |
| sentientos-chat | sentientos.chat_service:run | packaged_cli | operator-gated |
| sentientos-updater | updater:update | packaged_cli | operator-gated |
| sosctl | sosctl:main | packaged_cli | operator-gated |
| verify_audits | sentientos.verify_audits:main | packaged_cli | operator-gated |
| audit_immutability_verifier | sentientos.vow_artifacts:run_immutability_verifier_main | packaged_cli | operator-gated |
| reconcile_audits | scripts.reconcile_audits:main | packaged_cli | operator-gated |
| sentientos-reviewer-proof-bundle | scripts.build_reviewer_proof_bundle:main | packaged_cli | operator-gated |
| python -m sentientos | sentientos.__main__ | module_cli | operator-gated |
| python -m sentientos.audit | sentientos.audit.__main__ | module_cli | operator-gated |
| python -m sentientos.cathedral | sentientos.cathedral.__main__ | module_cli | operator-gated |
| python -m sentientos.federation | sentientos.federation.__main__ | module_cli | operator-gated |
| python -m sentientos.node | sentientos.node.__main__ | module_cli | operator-gated |
| python -m sentientos.ops | sentientos.ops.__main__ | module_cli | operator-gated |
| python -m scripts | scripts.__main__ | module_cli | operator-gated |

Reachability here means a declared packaging or `__main__` root. It does not imply routine use, installation as an OS service, default enablement, or effect authority. Modules reached only by tests, demos, explicit scripts, or historical aliases remain separately classified.

## 5. System architecture map

```text
operator/configuration
        |
        v
 supported entrypoint ----> composition root ----> evidence/read models
        |                         |                        |
        |                         v                        v
        |                 definitions / policy      proposals/review
        |                         |                        |
        +-----------------> grant + feasibility + admission
                                  |
                                  v
                         execution custody / actuator
                                  |
                         attempted result + validation
                                  |
                           receipt / adoption (distinct)
```

There is no universal pipeline that every subsystem traverses. Local inference, external HTTPS, memory write, host fulfillment, repository mutation, and process replacement have distinct owners and missing/default-disabled stages.

## 6. Subsystem atlas

| ID | Purpose | Maturity | Liveness | Activation | Authority | Effect | Persistence |
|---|---|---|---|---|---|---|---|
| resident-runtime | Resident maintenance and evidence loop | implemented_bounded | resident_composed | default active | authority consumer only | metadata_only | JSON/JSONL |
| cognitive-cycle | Caller-driven goal selection, attention, simulation, narration and integration | implemented_bounded | library_only | operator-gated | none | no_effect | process-only |
| legacy-core | Earlier cognition orchestration | legacy_live | compatibility_only | compatibility | none | memory_effect | JSON/JSONL |
| canonical-memory | Durable governed conversation retention and retrieval | implemented_bounded | service_composed | authority-gated | authoritative state writer | memory_effect | JSON/JSONL |
| legacy-memory | Compatibility memory, summaries and indexes | compatibility | compatibility_only | compatibility | authority consumer only | memory_effect | database/index |
| prompt-context | Context hygiene and selected memory assembly | implemented_bounded | library_only | operator-gated | authority consumer only | metadata_only | process-only |
| screen-audio-perception | Screen/OCR/audio/speech/vision observations | partial | operator_invoked | environment-gated | observation | observation_only | JSON/JSONL |
| embodiment | Ingress, fusion, avatar and expression representations | partial | library_only | config-gated | proposal | proposal_only | JSON/JSONL |
| household-presence | Inventory, zone and camera-policy metadata chain | implemented_bounded | operator_invoked | operator-gated | validation | review_only | JSON/JSONL |
| world-state | Evidence-bound facts, conflict and freshness projection | implemented_bounded | resident_composed | default active | observation | observation_only | atomic file |
| control-plane | Definitions, grants, policy, admission and revocation | implemented_bounded | resident_composed | default active | admission | admission_capable | append-only ledger |
| trust-integrity | Audit trust, quarantine, privacy and evidence strength | implemented_bounded | library_only | authority-gated | validation | verification_only | hash-linked ledger |
| provenance | Digest, causal, generation and event lineage | partial | library_only | authority-gated | validation | verification_only | JSON/JSONL |
| host-observation | CPU, memory, disk, services and thermal evidence | implemented_bounded | resident_composed | default active | observation | observation_only | atomic file |
| host-effects | Admitted workspace, diagnostic and process effects | implemented_bounded | operator_invoked | authority-gated | execution custody | bounded_real_effect | append-only ledger |
| external-model | Exact HTTPS request under definition, grant, feasibility and admission | implemented_bounded | operator_invoked | unavailable default | execution custody | network_effect | append-only ledger |
| local-model | Catalog through serving, inference and durable chat | implemented_bounded | service_composed | operator-gated | execution custody | bounded_real_effect | atomic file |
| maintenance | Signals, Forge/Codex handoff, validation and adoption | partial | resident_composed | config-gated | adoption | repository_effect | repository |
| lifecycle-recovery | Shutdown, explicit recovery, supervision and replacement | partial | resident_composed | config-gated | adoption | process_effect | atomic file |
| federation | Node identity, trust epochs, replay and laboratory WAN | partial | CLI_only | operator-gated | proposal | simulation | JSON/JSONL |
| councils | Advisory councils, agents and demos | legacy_live | dormant | compatibility | proposal | proposal_only | JSON/JSONL |
| audit | Audit chain, verification and proof artifacts | implemented_bounded | CLI_only | operator-gated | validation | verification_only | hash-linked ledger |
| codex-workcell | Bootstrap, acceptance, matrix, landing and publication handoff | implemented_bounded | CLI_only | development-only | validation | repository_effect | repository |
| interfaces | CLIs, API, GUI, dashboards and services | partial | operator_invoked | operator-gated | authority consumer only | bounded_real_effect | JSON/JSONL |
| formal | TLA+ models and executable verification | partial | dormant | development-only | validation | verification_only | repository |
| cultural-legacy | Cultural and historical interfaces retained in tree | compatibility | compatibility_only | compatibility | none | no_effect | JSON/JSONL |

### Identity and models

System identity is not identical to a loaded model. Local lifecycle records distinguish catalog, custody, acquisition, commissioning, activation, serving, and per-generation inference admission. Runtime/generation identity allows inference machinery to be replaced without treating model text as authority. External-model execution has exact material, credential, feasibility, admission, HTTPS custody, response, and receipt surfaces, but is unavailable by default and not resident-composed.

### Cognition and councils

The current cognition surface is callable: goal selection, attention/arbitration, reflection/narration, simulation, and integration can be driven by a caller. Repository evidence does not establish it as a background `sentientosd` loop. Older core/runtime cognition and council/agent families remain mixed library, demo, or compatibility surfaces. A class or file called “autonomous,” “agent,” or “daemon” is not activation evidence.

### Memory and context

Canonical chat retention is a real durable mutation path under its own controls. Legacy memory managers, summaries, indexes, selective distillation, capsules, tombs, protection, and live-memory gates span several generations. Many late-stage live-memory records are plans, review gates, readiness envelopes, or sandbox adapters rather than proof of mutation of the canonical live root. Memory may influence prompt context; it cannot by itself satisfy deterministic machine truth, freshness, admission, or operator-consent predicates.

Context hygiene has deterministic selection, safety metadata, materialization, preflight, review, credential-custody, null transport, and denial chains. Older prompt/context routes are less uniformly digest-bound. This task did not modify `prompt_assembler.py`.

### Perception, embodiment, and household presence

Screen/OCR, audio/speech, vision/gaze, sensor provenance, privacy and retention concepts exist with adapter-specific maturity. Hardware availability, freshness, calibration, and retention are not uniform. Embodiment ingress/fusion and avatar/expression families often represent observations or proposals, not actuation. Household camera inventory/policy/review/denial/renewal chains are deterministic metadata; they explicitly defer live camera/media/speaker authority.

### World State, governance, and trust

The World-State Evidence Board projects sourced records, freshness and conflicts; it is not an omniscient or self-authorizing truth store. `ControlPlaneKernel` and `RuntimeGovernor` distinguish definition, grants, policy, feasibility, admission, revocation/supersession, execution custody, receipt, and adoption. Audit trust, pulse epochs, quarantine, privacy, evidence strength, calibration, and `untrusted_external_data` are real concepts but remain partly domain-specific rather than one universal ontology.

### Host observation and effects

Resident host-resource code observes CPU/memory/disk/service/thermal evidence and produces proposals/review material. Phase-one observation does not grant fan/PWM/thermal writes. Real filesystem, local diagnostic, subprocess, GUI, service and other actuator classes are inventoried separately; most are operator/authority gated and not resident defaults.

### Maintenance, lifecycle, and recovery

Maintenance signals, Genesis/Forge, Codex implementation, validation/correction, mutation handoff, successor readiness, continuity, quiescence and process-image replacement are bounded stages. Repository mutation is not merge; handoff is not adoption; successor readiness is not replacement. Configuration chooses at most one cadence owner. Some durable restart reconstruction exists, while universal unexpected-death recovery and automatic rollback are not established.

### Federation and formal assurance

Pulse/federation, identities, trust epochs, replay and laboratory WAN code exist; current default live WAN synchronization is not established. TLA+ specifications model selected runtime-governor, audit, federation and trust behavior. Their presence plus tests/checkers must not be described as formal verification of the whole Python system.

## 7. Capability-registry crosswalk

All {len(x['capability_crosswalk'])} registry records appear exactly once in the JSON atlas with their declared sources, proofs, implemented/deferred surfaces, forbidden implications, admission/operator/audit requirements, source/proof existence, and independently conservative composition/effect fields.

| Status | Count |
|---|---|
| blocked | 36 |
| deferred | 22 |
| implemented | 284 |
| partial | 11 |
| scaffolded | 2 |

The complete row set is intentionally machine-readable rather than reproduced as a 355-row prose table. `source_exists=false` or `behavioral_proof_exists=false` records expose evidence drift; they are not silently upgraded.

## 8. Authority/effect topology

| Domain | Observed chain | Important boundary |
|---|---|---|
| external-model-egress | evidence/config → authority definition → grant → feasibility → admission → execution custody → HTTPS attempt → result → receipt; no adoption | A later stage is never inferred from an earlier artifact. |
| local-model-inference | catalog/custody → commissioning → activation → serving → per-generation inference admission → opaque runner → conversation record | A later stage is never inferred from an earlier artifact. |
| memory-write | selected input → retention/protection policy → write admission → canonical mutation → retrieval | A later stage is never inferred from an earlier artifact. |
| host-fulfillment | observation → proposal → definition/grant/policy → readiness → admission → custody → effect → verification → receipt/rollback | A later stage is never inferred from an earlier artifact. |
| repository-mutation | signals → proposal → task authority → Codex workcell → validation → handoff → operator merge/adoption | A later stage is never inferred from an earlier artifact. |
| runtime-replacement | successor evidence → continuity → readiness → quiescence → exec replacement → post-exec proof/adoption | A later stage is never inferred from an earlier artifact. |

Domain differences matter: external HTTPS requires a network execution custodian; local inference is local but still generation-admitted; memory has retention/write controls; host fulfillment consumes exact authority; repository changes require workcell validation and handoff; process replacement requires quiescence, transition custody, and post-exec proof.

## 9. State and persistence topology

| State | Meaning | Authority | Writer | Storage | Digest | Freshness |
|---|---|---|---|---|---|---|
| canonical-memory | conversation history | authoritative within memory domain | conversation memory service | JSON/JSONL | record/schema checks | retrieval semantics |
| legacy-memory-indexes | summaries/indexes | derived | legacy memory managers | database/index | varies | weaker/legacy |
| audit | event evidence | authoritative audit record | audit logger | append-only ledger | hash-linked | sequence/time |
| audit-trust | trust posture | authoritative trust state | audit verifier | atomic file | digest bound | epoch/current verification |
| admissions | effect eligibility | authoritative admission | ControlPlaneKernel | JSON/JSONL | digest bound | expiry/revocation |
| grants | delegated authority | authoritative grant | grant issuer/operator chain | JSON/JSONL | digest bound | expiry |
| revocations | authority invalidation | authoritative | control plane | append-only ledger | digest bound | current sequence |
| fulfillment-consumption | single-use authority | authoritative | fulfillment custodian | append-only ledger | digest bound | consumed state |
| world-state | evidence board snapshot | derived/advisory | WorldStateBoardBuilder | atomic file | source digests | explicit observed-at/conflicts |
| host-observations | host facts | observation | host runtime | atomic file | evidence digests | sample time |
| model-state | activation/serving identity | authoritative for model route | model lifecycle controllers | atomic file | digest bound | generation/currentness |
| external-receipts | network attempt/result | evidence | execution custody | append-only ledger | request/response digests | attempt time |
| maintenance-state | generation/adoption | authoritative per maintenance domain | maintenance owners | repository | commit/digest bound | generation identity |
| wake-state | scheduler/wake state | operational | maintenance owners | atomic file | config digest | cadence time |
| quarantine | isolated records | authoritative restriction | integrity subsystem | JSON/JSONL | digest bound | incident state |
| runtime-caches | reconstructible projections | derived | runtime components | reconstructible cache | not uniformly | process/generation |

Authenticated domains fail closed on corruption; legacy domains vary. “Survives restart” does not mean “current”: snapshots and observations need timestamp/epoch semantics. Cognition and model output cannot directly make these domains authoritative merely by emitting plausible text.

## 10. Epistemic, truth, and provenance topology

* Model output may enter canonical conversation memory when the memory path admits it, or become a bounded proposal/receipt input where a deterministic constructor permits it.
* Selected memory may become prompt context; retrieval relevance is not machine truth.
* Model output does not alone become a grant, admission, operator approval, authoritative observation, current configuration, or adoption record.
* External observation becomes evidence through adapter/source identity, capture time, privacy/classification, digest or lineage, and domain validation. Older adapters may omit some of these.
* Confidence estimates uncertainty; authority identifies who may decide or act. Provenance describes lineage; trust evaluates custody/integrity. None substitutes for the others.
* Staleness appears through observed-at times, validity windows, trust epochs, current-generation bindings, and board freshness. Contradictions appear as explicit board conflicts in hardened surfaces; older stores may merely retain inconsistent rows.

## 11. Automation/background-loop inventory

| Loop | Class | Starter | Wake | Model | Can execute | Restart | Production composed |
|---|---|---|---|---|---|---|---|
| sentientosd-loop | actual_current_background_loop | sentientosd main | interval/event shutdown | governed local advice only when configured | metadata and configured maintenance stages | persistent artifacts; process-local scheduler | True |
| maintenance-scheduler-owner | callable_operator_invoked_loop | sentientosd with adoption config | configured cadence | optional | proposal/handoff chain | adoption file | True |
| maintenance-wake-owner | callable_operator_invoked_loop | sentientosd with exclusive adoption config | configured cadence | no direct claim | wake/adoption coordination | adoption file | True |
| successor-generation-owner | callable_operator_invoked_loop | sentientosd with exclusive successor config | configured | optional downstream | adoption/process transition coordination | durable config/state | True |
| pulse-federation | historical_legacy_named_daemon | explicit library/CLI caller | configured | none | federation messages when separately configured | JSON | False |
| dream-reflex-council-families | scaffolds_tests | explicit callers/tests | none established | varies | not resident by name alone | UNKNOWN / NOT ESTABLISHED | False |

Only `sentientosd` starts unconditionally when that entrypoint is launched. The maintenance owners are callable from the resident composition but require exact, mutually exclusive config. Historical daemon names and test fixtures are not counted as automatically running.

## 12. Real-effect inventory

| Effect | Implementation | Authority | Default | Production reachable | Actuator only/uncomposed |
|---|---|---|---|---|---|
| filesystem-mutation | sentientos/workspace_file_effect.py | authority-gated | False | False | True |
| repository-mutation | sentientos/repository_mutation_handoff.py | operator/adoption gated | False | False | True |
| process-replacement | sentientos/maintenance_resident_runtime_adoption.py | config and authority gated | False | False | True |
| subprocess-control | sentientos/bounded_subprocess.py | caller/admission gated | False | False | True |
| gui-input | api/actuator.py | operator/control gated | False | False | True |
| network-egress | sentientos/external_model_https_transport.py | definition+grant+feasibility+admission | False | False | True |
| local-model-invocation | sentientos/local_model_serving_inference.py | commissioning+activation+serving+inference admission | False | True | False |
| external-model-invocation | sentientos/external_model_execution_custody.py | definition+grant+feasibility+admission | False | False | True |
| memory-mutation | sentientos/canonical_memory.py | memory policy/admission | True | True | False |
| credential-read | sentientos/external_model_custody.py | execution custody only | False | False | True |
| hardware-device-actions | sentientos/builtin_local_effect_runner.py | bounded admitted contracts; actuator-specific | False | False | True |
| service-restart | sentientos/goal_executor.py | operator/admission gated | False | False | True |
| federation-transport | sentientos/daemons/pulse_federation.py | explicit configuration; not resident default | False | False | True |

“Production reachable” is conservative and still does not assert that an effect occurred. Most behavioral tests use fakes, temporary files, synthetic credentials/admissions, dry-run executors, in-memory backends, or null hardware/network adapters. That proves bounded code behavior, not deployment state.

## 13. Platform map

| Platform | Posture |
|---|---|
| POSIX | primary; exec replacement supported |
| Windows | supported in bounded modules; durability/process semantics differ |
| Docker/devcontainer | development configuration, not proof of production service installation |

Installation remains a collection of explicit operator procedures rather than proof of an installed persistent OS service. POSIX process replacement can use exec semantics; Windows uses separate bounded service/readiness surfaces and has documented durability differences.

## 14. Architectural eras

| Era | Assumption | Current consumption | Superseded by | Surviving concepts |
|---|---|---|---|---|
| cultural-runtime | expressive modules and direct compatibility CLIs | compatibility/manual surfaces | governed package/runtime composition | ritualized audit vocabulary, operator ceremony |
| modular-agent-cognition | callable cognition, councils and memory managers | mixed library/compatibility | explicit service and control-plane composition | reflection, memory, advisory councils |
| governed-control-plane | authority definition, grant, admission and receipts are distinct | resident and operator paths | current; increasingly specialized custody chains | fail closed, auditability |
| effect-custody-and-adoption | effect execution and adoption require exact, domain-specific custody | bounded current composition/config-gated paths | none established | operator authority, evidence binding |

Age alone did not determine classification. Packaging declarations, `__main__` roots, imports/constructors, resident composition, tests, and compatibility entrypoints supplied evidence. Cultural vocabulary survives, but newer control/effect custody is not inferred from ritual terminology.

## 15. Legacy and compatibility map

| Family | Files | Status | Material to current architecture | Representative paths |
|---|---|---|---|---|
| architecture-machine-readable | 4 | current/supporting/mixed | False | architecture/authoritative_state_evidence_custody.json, architecture/council_lineages.json, architecture/historical_surface_dispositions.json |
| configuration-manifests-platform | 61 | current/supporting/mixed | True | .devcontainer/Dockerfile, .devcontainer/devcontainer.json, .github/CODEOWNERS |
| cultural-avatar-cathedral-legacy | 127 | legacy/compatibility mixed | False | LEGACY_RITUAL_DRIFT.md, RITUAL_FAILURES.md, archive_blessing.py |
| documentation | 684 | current/supporting/mixed | False | docs/ACTUATOR.md, docs/AGENTS_DOCTRINE_ARCHIVE.md, docs/ARCHITECTURE.md |
| formal-specifications | 9 | current/supporting/mixed | False | formal/README.md, formal/models/audit_reanchor.json, formal/models/federated_governance.json |
| neos-resonite-legacy | 208 | legacy/compatibility mixed | False | neos_archive_exporter.py, neos_artifact_blessing_reconciler.py, neos_artifact_curation_suite.py |
| other-repository-assets | 321 | current/supporting/mixed | False | .codex_task/bootstrap.plan.json, .codex_task/bootstrap.prompt.txt, .codex_task/bootstrap.scaffold.json |
| scripts | 455 | current/supporting/mixed | False | scripts/__init__.py, scripts/__main__.py, scripts/add_codex_request.py |
| sentientos-package | 853 | current/supporting/mixed | True | sentientos/__init__.py, sentientos/__main__.py, sentientos/actuation_fulfillment.py |
| tests | 2614 | current/supporting/mixed | False | sentientos/tests/conftest.py, sentientos/tests/federation/test_digest_with_sanitizer.py, sentientos/tests/federation/test_federation_consensus.py |
| top-level-and-compatibility-python | 545 | legacy/compatibility mixed | False | .env.sync.autofill.py, Liturgy/__init__.py, actuator.py |

The JSON preserves every tracked member of each family. Neos/Resonite, avatar, cathedral, blessing/ritual/saint, festival, council and top-level compatibility surfaces were not discarded. Their operational status is mixed: some have shipped CLIs, some are demos/libraries, and some are disconnected or unknown. Public documentation may acknowledge this cultural/compatibility layer without presenting it as the current authority architecture.

## 16. Synthetic/test versus production

Synthetic transports, fake networks/credentials, temporary ledgers, test admissions, dry-run executors, fixtures, in-memory stores, no-hardware adapters, and unavailable/null defaults occur extensively. Tests are legitimate implementation evidence. They do not show that a production resident starts the component, that a grant exists, that credentials exist, that hardware is present, or that an effect occurred. Capability records and surfaces therefore keep `behavioral_proof_exists`, `production_runtime_composed`, `effect_enabled_by_default`, and `actual_effect_possible` separate.

## 17. Current gaps and UNKNOWNs

| Gap | Classification | Evidence-bounded statement |
|---|---|---|
| external-default | missing runtime composition | External-model custody exists without resident/default grants, credentials, or provider configuration. |
| live-camera | intentionally deferred | Household camera chain remains metadata/review; live capture is deferred. |
| host-default | registry-blocked | Host real-effect runners do not follow from resident read-only observation. |
| provenance-legacy | provenance gap | Older free-form surfaces do not uniformly preserve digest-bound lineage. |
| freshness-legacy | freshness gap | Older telemetry may lack uniform currentness semantics. |
| universal-recovery | missing recovery | Automatic rollback and unexpected-death recovery are not universal. |
| federation-live | unknown | UNKNOWN / NOT ESTABLISHED: supported production WAN synchronization deployment. |
| public-drift | documentation drift | Forward docs need qualification against newer authority and composition boundaries. |

Additional UNKNOWN / NOT ESTABLISHED items include third-party use of legacy entrypoints, a complete deployed hardware inventory, universal provenance across historical records, and a current supported production WAN deployment. These are unknown rather than guessed.

## 18. Claims we can and cannot safely make

| Claim | Safety | Basis |
|---|---|---|
| persistent | safe only with qualifier | Persistence varies by domain. |
| model-agnostic | safe only with qualifier | Identity is separable; model routes are commissioned. |
| autonomous | safe only with qualifier | Resident loops exist; effects remain gated. |
| self-maintaining | safe only with qualifier | Maintenance is configured and independently adopted. |
| self-modifying | safe only with qualifier | Repository effects use a governed workcell. |
| introspective | safe only with qualifier | Evidence-board introspection is not omniscient truth. |
| embodied | safe only with qualifier | Many surfaces are representation/review only. |
| perception-capable | safe only with qualifier | Adapters and hardware maturity vary. |
| world-state aware | safe only with qualifier | Board tracks evidence, conflicts and freshness. |
| model-independent identity | safe as written | Runtime/generation identity is separate. |
| live memory | safe only with qualifier | Canonical chat path is live; others vary. |
| governed action | safe as written | Named effect paths have explicit custody. |
| host control | safe only with qualifier | Observation is default; actuation is gated. |
| external-model capable | safe only with qualifier | Implemented but unavailable by default. |
| network capable | safe only with qualifier | Specific gated transports only. |
| crash resilient | safe only with qualifier | Recovery is not universal. |
| distributed | safe only with qualifier | Federation exists without established default live sync. |
| multi-agent | safe only with qualifier | Libraries/councils are not resident defaults. |
| formally verified | not currently supported | Specs are not whole-system proof. |
| reference-monitor-like | safe only with qualifier | Only composed mediated domains. |
| runtime-assurance-like | safe only with qualifier | Bounded named contracts. |
| recursive self-improvement | explicitly disallowed/misleading | No autonomous recursive authority chain. |
| sentient/conscious | explicitly disallowed/misleading | Not established by repository evidence. |

## 19. Coverage and completeness answers

| Question | Answer |
|---|---|
| Every capability registry record classified? | Yes: exact-once 355-row crosswalk. |
| Every supported package/CLI/service entrypoint mapped? | Yes for packaging scripts and discovered package `__main__` roots; undocumented third-party invocation is UNKNOWN. |
| Every resident/background loop classified? | Yes for current composition and material named daemon families. |
| Every known real-effect class inventoried? | Yes, conservatively; actuator presence is separate from composition. |
| Every major persistent state domain mapped? | Yes: 16 domains. |
| Local and external model paths traced? | Yes. |
| Old/new memory distinguished? | Yes. |
| Maintenance and runtime adoption traced? | Yes. |
| Neos/Resonite/avatar/cathedral classified? | Yes, including exhaustive path-family members in JSON. |
| Claims reconciled against source? | Yes; source/composition and tests outrank prose. |
| Ambiguity explicit? | Yes; unresolved facts say UNKNOWN / NOT ESTABLISHED. |

## 20. Evidence and navigation appendix

Primary composition and contract anchors:

* `sentientosd.py` — resident root and configured maintenance owners.
* `pyproject.toml` — packaged interfaces and dependency groups.
* `sentientos/capability_registry.py` — complete bounded capability declarations.
* `sentientos/control_plane_kernel.py` and `sentientos/runtime_governor.py` — authority/admission mechanics.
* `sentientos/local_model_serving_inference.py` and `sentientos/chat_service.py` — current local serving/chat.
* `sentientos/external_model_execution_custody.py` and `sentientos/external_model_https_transport.py` — gated external execution.
* `sentientos/world_state_board.py` and host runtime modules — evidence projection and resident host observation.
* `sentientos/maintenance_resident_runtime_adoption.py` — process transition custody.
* `architecture/current_repository_system_atlas.json` — exact crosswalks, tracked-family members, classifications, and evidence paths.
* `docs/architecture/forward_documentation_reconciliation_docket.md` — action docket; not replacement public prose.

### Method limits

This analysis used the current repository and its executable/test/document evidence only. It did not contact providers, inspect live credentials, exercise live network effects, or use external comparator architectures. Static reachability and tests cannot establish every deployment or third-party caller. Such limits remain explicit rather than being resolved toward the more impressive interpretation.
