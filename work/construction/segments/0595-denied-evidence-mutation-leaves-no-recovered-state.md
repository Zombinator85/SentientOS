# Sequence 595 — denied evidence mutation leaves no recovered state

PR #2647 extends sequence 594's cross-proposition denial regression to durable side effects. After a foreign support binding is rejected, the test asserts that the target proposition retains its prior unknown state and update-event history, and that no state mutation intent or receipt was added. It then reconstructs the owner and mutation controller from disk and confirms recovery still reports the same unknown state and event history.

The test preserves the audit record for the attempted authority request while proving that candidate evidence validation fails before mutation admission, intent publication, or state receipt creation. Existing positive/adverse outcome planning, exact model identity, and non-executing canonical planning coverage remain in place. No production code, inference, or authority changed.

The exact source candidate is `28c4f199fdf84512bb055e0215e3b5ad4a392e32`, tree `2798dc0d71fe0ca0475be8d564884e813ef429d7`, based on verified main `bcd08db8d25a26a0f7146ccdfe11b1e33e9ba41e`. The full pytest suites passed in CI and Lint Benchmark, and integrated source acceptance passed.

All eight exact-candidate workflows passed: CI 39874439023, Required Quality Gate 39874439175, Release 39874439109, Codex CI 39874439120, Gradient null regression 39874439017, Invariant Tests 39874438997, Docker Image 39874439116, and Lint Benchmark 39874439079. The strict gate passed Administrator audits, exact acceptance binding, audit immutability, hosted finalization, and the separate metadata guard.

PR #2647 merged normally as `e33987f53a9e17a71f098cfa58fb0324353a3c05`. Its tree is `2798dc0d71fe0ca0475be8d564884e813ef429d7`; the candidate is the second parent and the merge introduced no tree changes beyond the candidate. No production goal execution or model inference occurred.

Sequence: 595 (verified source integration)
