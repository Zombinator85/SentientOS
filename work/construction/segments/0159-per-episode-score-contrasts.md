# Sequence 159 — Expose exact score contrasts per episode

**Source:** `103b098be19b1d01c5f9890d6a29437d6d8e3ddd`  
**Tree:** `78f6e04de83811fa6e5e13aa95077e9d30bfa470`

The read-only progression report now emits, per episode, the history-present minus history-withheld and restored minus present correct-count differences, their exact held-out probe denominator, and a scoreable/unscoreable posture. Missing or truncated condition scores produce `None` deltas instead of a fabricated zero. Each contrast explicitly states that it establishes neither learning nor performance improvement.

Focused positive, adverse, unscoreable, and acquired-history episode tests passed (**3 passed in 67.82s**); changed Python compiled. All model behavior remained deterministic fixture behavior.

Next: strengthen cold-process reconstruction of the acquired-history progression itself; existing subprocess recovery covers progression custody but the full positive acquired-history chain currently reopens a new owner in-process.
