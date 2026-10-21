# Sequence 533 — repair operator clock acceptance binding

The first hosted candidate on PR #2543 ran the naive/offset-unknown regression but failed exact acceptance because its parameterized pytest node was recorded under expanded case IDs while the manifest named the unsuffixed function. The case IDs are now stable (`naive_clock` and `offset_unknown_clock`) and both exact cases are selected independently by source validation and acceptance. No requirement was removed or relaxed.

The same timestamp boundary now captures one explicit UTC offset and uses that offset to normalize the sampled instant, avoiding a second `tzinfo` callback during `astimezone()` conversion. The direct provenance verifier uses the same captured-offset conversion, so a dynamic timezone object cannot change the observed instant mid-validation. An adverse regression exercises that path and verifies a single offset read.

Local verification passed 47 tests in the affected operator module, five focused regression/acceptance cases, compilation, and targeted Mypy with imported legacy modules excluded (no diagnostics in either touched production module). A clean full import-graph Mypy comparison against exact base main produced 339 diagnostics across 64 files on both base and candidate; no new diagnostics were introduced. Hosted checks for the corrected candidate are pending.

The active checkpoint was compacted to remain within its 64 KiB reader bound; the removed historical narrative remains in the append-only segment and evidence chain.

No production transition, activation, serving, inference, or writeback was performed.

Verified base main: `9f240e177afc7eb7b67c05e33ca5283b2d8cd598`, tree `38479e185d368011ef331458de875e15746a0643`
Implementation candidate: `81fdce1661007e5ea45c299bad25f866e2808de6`, tree `aaee662d942d4754c1859f756a01c052d2353a7a`
Latest construction segment: `work/construction/segments/0533-repair-operator-clock-acceptance-binding.md`
Sequence: 533 (candidate pending hosted verification)
