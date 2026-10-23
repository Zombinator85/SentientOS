# Sequence 606 — Fail-closed federation peer configuration parsing

The federation stream relay's `load_peers()` assumed that the YAML document was a mapping and every row under `peers` had a `.get()` method. A scalar or list root, a non-list `peers` value, or a malformed row could raise before the relay started any peer worker.

PR #2671 makes the parser fail closed: non-mapping roots and non-list peer collections produce no peers; malformed rows and non-string or blank URLs are skipped; valid URLs are trimmed and retained in order. Existing valid configuration behavior is preserved.

The exact source and regression file compiled locally. The focused suite passed 21 tests, covering malformed roots and YAML, invalid peer collections, malformed rows, invalid URLs, valid URL trimming, the bounded stream framer, and its response-loop wiring. The hosted exact-candidate Quality Gate passed strict Administrator audits, exact acceptance, hosted finalization, and the separate metadata guard; source validation, self-check, docs, Helm, invariants, lint, build, and CPU smoke also passed.

PR #2671 merged normally as `7a47004a30d41953436df4266d799b0cbb9d6973`, tree `d9c38f8004301014562f9533e30fea9bc69ebdb6`, first parent main `e85508898c78cdaecfebc204ab19f7aed1a8bd4a`.

This only makes local configuration parsing robust. Federation peers remain unauthenticated, event freshness remains unestablished, and relay output remains separate from the Federation Health input. No live telemetry or healthy status is inferred.

The next delayed scheduled Federation Health run, #39902569701, executed on exact main `7a47004a30d41953436df4266d799b0cbb9d6973`. Hosted Administrator preflight, generation, report receipt binding, and artifact upload passed. The repository-scoped GitHub App publisher then created PR #2672 with the run-bound receipt; the receipt-only PR passed its checks and merged normally as `63a6155c83c41b481f0274c877c1fc8fc803d4cb`. The report remains stale: one configured node, zero events in 24 hours, latest recorded event 2025-06-05T16:25:13.805813Z. This is execution/publication evidence, not live federation health.

Sequence: 606 (fail-closed relay configuration parsing; no authenticated telemetry, production transition, model inference, or goal execution)
