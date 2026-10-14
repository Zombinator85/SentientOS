## 2026-10-14 checkpoint — isolate the Codex subject and scorer destinations

- Built from verified sequence-179 evidence HEAD `14d4eff88858b06791f8ae7c791d8c8b7e421ce1`, tree `2d998db83bb34df6ea6822ad47fd204233d1622f`. Published source commit `747998e0d595b9a22d259f2a2464f2f2930cd126`, tree `f049ec96de3ed0754118509d8ae086cb55abd101`.
- Replaced the shared output root with required, non-overlapping subject packet directory, scorer-only directory, and separate preregistration file destinations. The builder rejects equal/nested destinations and existing directories. The subject-facing directory contains only opaque packet JSON files.
- Extended the operator procedure and tested successful output layout plus path-overlap rejection through the builder entry point.
- Validation: 72 focused packet/scorer, history-intervention, writeback, strategy, and consequence tests passed; four additional task-family staging/admitted-history/progression/restart tests passed; targeted mypy, compilation, CLI help, and diff checks passed.
- No external Codex sessions, real-model results, production behavior, or unauthorized effects. This is an experimental custody improvement only.

Next: implement the narrow operator-mediated blinded strategy packet path by reusing the existing `EmbodiedStrategyProposal`, history intervention conditions, and independent strategy scorer. Require verified admitted consequence lineage and keep evaluator-only information separate; do not infer execution authority or claim fixture results as genuine-model evidence.
