# Sequence 350: merge and verify the handoff fixture repair

## Candidate and merge identity

Candidate `9b96dfd2f2869f62393926fdb25248aed0889366`, tree `0b698550ca6bfb9786f55e4d3c0515cafec8f3c1`, changed only `tests/test_local_model_chat_runtime_startup.py`. PR #2340 was merged normally into main `3696b2aeb9fab43629cf037fc7337db0d0d2b0a9`, tree `0b698550ca6bfb9786f55e4d3c0515cafec8f3c1`, with parents `617fdad39833c05cf0e0a1784d46e59a73cfd5b3` and `9b96dfd2f2869f62393926fdb25248aed0889366`.

Candidate CI `39096570563`, Required Quality Gate `39096570615`, Docker `39096570599`, invariants `39096570461`, Codex CI `39096570551`, Lint Benchmark `39096570648`, Release `39096570529`, and Gradient `39096570486` all succeeded. QG artifact `12124033234` has digest `sha256:3689bc72707c062c1f2ed10183f18a86d8436cb2c9fe9caa61091d7fd60162c8`; hosted finalizer artifact `12124267804` has digest `sha256:9a4b3392d3eaccbc9c9f639546b92adba5dc980ddbc63bf3e7ea1203279567f2`.

## Post-merge verification

On exact main `3696b2aeb9fab43629cf037fc7337db0d0d2b0a9`, CI `39096860813`, Required Quality Gate `39096860870`, Docker `39096860848`, invariants `39096860887`, Codex CI `39096860917`, and Docs Deploy `39096860860` all succeeded. Forge Smoke `39096860866` was skipped by configured conditions. Post-merge feedback run `39096861173` succeeded. Independent QG artifact `12125335451`, digest `sha256:6be2fcd26968eba2b08966bcb093f53b5b05c20d79c0b7a1220c4d0cea051cb1`, confirms 29/29 required nodes passed, effective UID 0, exact source SHA/tree, Administrator verification, successful strict and immutability audits, and unchanged repository identity.

## Operational status

At 2026-10-18 04:26 UTC, the Actions feed still had no scheduled Federation Health, Nightly Audit Integrity, or Nightly Self Check run on main `3696b2aeb9fab43629cf037fc7337db0d0d2b0a9`. The newest observed scheduled runs remain on older source: Federation Health `39083395122` (`7d19f2651e8b09bd614322a1ba4ad8b2ae014218`), Nightly Audit `39014123936` (`50d062baab7f838b1dfeaf9b79ec42c5da0e0a14`), and Nightly Self Check `38876666946` (`d8d7a219221cd94240accf7991fe353b14f6a84e`). Their strict Administrator requirements and least-write scopes remain intact. The connected GitHub tools cannot dispatch Actions; no current-source scheduled execution or changed-output publication is claimed. No production model transition or improvement is claimed.
