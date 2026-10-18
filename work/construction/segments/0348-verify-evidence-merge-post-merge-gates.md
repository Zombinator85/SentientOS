# Sequence 348: verify evidence integration and post-merge gates

## Evidence integration

Sequence 347's evidence ledger was published as PR #2338 with evidence commit `ca009679fc53f49ec19b2f89c9c17f020f3b16a9`, tree `d80c66f0ebbeee9126856db9a2ad7ad6e917f6ec`, based on main `06b1b3cbf5424b4e05cc3f0274b5ce5646f7fbda`. The PR was merged with the regular merge method. Resulting main is `c83aa80d6776024af8e39011f3698c6e3c7afd9a`, tree `d80c66f0ebbeee9126856db9a2ad7ad6e917f6ec`, parents `06b1b3cbf5424b4e05cc3f0274b5ce5646f7fbda` and `ca009679fc53f49ec19b2f89c9c17f020f3b16a9`. The index and segment additions are append-only; no source or authority policy changed.

## Hosted verification

On the evidence PR head, CI `39095025384`, Required Quality Gate `39095025397`, Docker `39095025382`, invariants `39095025363`, Codex CI `39095025404`, Lint Benchmark `39095025393`, Release `39095025365`, and Gradient null regression `39095025452` all succeeded. The QG artifact `12123319500` has GitHub digest `sha256:a9f22625a5f554efaababf312f1499ec76ff6d21150b7a3eac20512166a0a9a8`; hosted finalizer artifact `12124152053` has digest `sha256:eaae986815cd2bcff6ec3e841d031bcb2ffb1a145c6ee0ef58d877259a4eb3d4`.

After merge, CI `39095268117`, Required Quality Gate `39095268143`, Docker `39095268132`, invariants `39095268136`, Codex CI `39095268116`, and Docs Deploy `39095268109` succeeded on exact main `c83aa80d6776024af8e39011f3698c6e3c7afd9a`; Forge Smoke `39095268200` was skipped by configured workflow conditions. Post-merge feedback run `39095268032` succeeded. Independent QG artifact readback confirms effective UID 0, exact source SHA/tree, strict audit and immutability validation success, and unchanged repository identity. Its artifact `12123929332` has GitHub digest `sha256:5142c61c21da425c05278215ff4a797210f228ef231c6a787222318781dee034`.

## Operational evidence still pending

As of 2026-10-18 04:03 UTC, the Actions feed has no scheduled Federation Health, Nightly Audit Integrity, or Nightly Self Check run on this main. The newest Federation Health run is still `39083395122` on older source `7d19f2651e8b09bd614322a1ba4ad8b2ae014218`; the latest Nightly Audit is `39014123936` on `50d062baab7f838b1dfeaf9b79ec42c5da0e0a14`; the latest Nightly Self Check is `38876666946` on `d8d7a219221cd94240accf7991fe353b14f6a84e`. Current main retains their tested strict Administrator calls and least-write scopes. This GitHub connector provides no workflow-dispatch operation and local GitHub CLI authentication is unavailable, so current-source scheduled execution and changed-output publication are not claimed. No production model transition or developmental benefit is established.
