# Sequence 665: Reconcile roadmap freshness checks with the history archive

The compact roadmap index states that consumed history is archived, but its verifier checked only the compact index. On verified main that produced 55 violations because historical PR markers, blocked surfaces, bootstrap wording, and custody language were no longer duplicated in the index. The old candidate-table checks also treated archived options as active selection.

This candidate makes file verification follow the declared sibling archive for consumed history and stable controls, keeps available-work checks on the active index, binds both files in a canonical source-input manifest, and reports both input digests. Focused regression passed 29 tests with zero failures; both required file-level behavior nodes passed exact task acceptance. Targeted mypy, docs dependency checking, the 616-page docs build, and `git diff --check` passed. The verifier reports zero roadmap violations.

The canonical full local regression attempt stalled at about 39% for roughly six minutes and was stopped without a completion summary or finalized provenance. It is not counted as a pass. The exact current main's hosted CI source validation and docs checks passed after sequence 663; this candidate still requires its own exact-head hosted Quality Gate and CI before landing.

Base main: `46cabb0dbb4a5230c29477702c319e49b2985353`, tree `239b673d680b720ae549d7f8b2f854316ce474a`
Candidate remains uncommitted and unpublished. No runtime or repository authority was added by the verifier.
