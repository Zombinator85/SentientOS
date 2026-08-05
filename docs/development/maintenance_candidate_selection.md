# Maintenance candidate selection

Canonical maintenance candidates (`sentientos.maintenance_candidate:v1`) are metadata-only records derived from source records. They are not source subsystem receipts and they never admit, start, execute, validate, mutate, commit, publish, lease, or adopt work.

Semantic identity binds candidate kind, normalized objective, subject paths, base SHA/source contract, requested authority classes, declared constraints, and semantic source identity. Custody fields such as timestamps, artifact locations, input order, JSON key order, and duplicate evidence order do not change identity. Exact duplicates collapse with sorted evidence and recurrence. Shared identity with material disagreement becomes `candidate_contradicted` and is blocked.

Adapters are side-effect-free for governed improvement signals, normalized work-item packets, stable Genesis need/proposal metadata, and explicit future canonical mappings. They preserve source identity and evidence, use declared targets, treat Genesis as metadata only, and reject false authority claims.

Candidate sets (`sentientos.maintenance_candidate_set:v1`) contain input source counts, canonical candidates, duplicate groups, contradictions, blocked candidates, and an aggregate digest. Input order does not affect bytes.

Selection uses an explicit caller policy (`sentientos.maintenance_candidate_selector_policy:v1`) with base SHA, allowed prefixes, forbidden patterns, available authority classes, file/diff/runtime/validation budgets, allowed kinds, optional severity, and reconsideration settings. The selector never reads ambient credentials or infers authority from the environment.

Eligibility uses stable reason codes for unknown scope, disallowed/forbidden paths, unavailable authority, disallowed kind, base mismatch, budget excess, contradiction, blocked source, insufficient evidence, active/resolved work, reconsideration requirements, and unhealthy journals. Maintenance-task journals are read from an explicit external state root and are never appended by selection.

Journal lifecycle classification is: no matching task is pending; created/nonterminal, active lease, or active attempt is active; closed is resolved; cancelled is cancelled; blocked is blocked; failed integrity is journal unhealthy. Active and resolved candidates are not selected. Cancelled or blocked candidates require explicit reconsideration and either a changed candidate revision or a token; reconsideration does not broaden scope or authority.

Ranking eligible candidates uses a deterministic tuple: operator priority, severity, recurrence count, confidence, lower scope cost, and candidate ID as final tie-breaker. It does not use clocks, filesystem enumeration, Python hash order, ingestion order, randomness, mutable globals, or model judgment.

Selection artifacts (`sentientos.maintenance_candidate_selection:v1`) include policy and candidate-set digests, journal references, eligible/ineligible IDs, ranked IDs, selected candidate metadata, resource estimates, result status, and selection digest. `ready_for_scope_admission` means only that the next authority-lease task may consider the proposal. `idle_no_viable_candidate` is a truthful successful idle state when policy and journals leave no viable candidate.
