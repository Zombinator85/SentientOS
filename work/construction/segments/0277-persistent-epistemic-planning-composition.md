# Sequence 277 — Compose the verified epistemic owner through canonical daemon planning

Sequence 276 is merged as `c0ec52ce695d74ad7d8f970081790ff86bad7acf` with exact tree `240bec26d5473acb501de24a9dbdbb93aea80cd2`. This increment strengthens the existing planning acceptance case by passing a real `PersistentEpistemicStateOwner` through `RuntimeMaintenanceSurfaces.plan_canonical_goals`. The owner's verified prior position changes the canonical allocation: the proposition-scoped goal is deferred for review and an independent goal remains selected.

The same test captures the owner state before and after planning, checks it remains unchanged, and makes both serving-session acquisition/model invocation and executor execution fail immediately if attempted. This closes the gap between the owner-to-planner behavior test and the daemon wiring test while preserving the plan-only authority boundary.

Local verification on the construction workspace: the focused case passed 1/1, the complete plan-only module passed 5/5, Python compilation passed, and `git diff --check` passed. These local provenance records identify the workspace's stale Git HEAD `d8d7a219221cd94240accf7991fe353b14f6a84e`; the source had uncommitted construction changes and is therefore not represented as exact-source verification. Fresh hosted CI on the published candidate is required for exact-source acceptance. The sequence 276 full hosted run and UID-0 strict audit remain the verified baseline.

Next: publish this bounded regression on the current main lineage, require the hosted planning acceptance and strict audit on its exact source, then continue F1-F8. External sessions and physical outcomes remain unverified.
