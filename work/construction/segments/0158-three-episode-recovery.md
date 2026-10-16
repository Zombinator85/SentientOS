# Sequence 158 — Verify the integrated three-episode history loop

**Source:** `d40f008dd72ba736292f0dcb6702f97640ce9ff9`  
**Tree:** `383dc4a0c87b6b2de44ad9eef1d2af65bb94c916`

Extended the existing source-backed task-family fixture to assert exact relevant-history record IDs for three distinct scored task instances. Episode one is a baseline with no admitted matching family record; episode two uses the admitted source outcome; episode three uses both the original acquired record and the separately admitted feedback record. Present and restored retrieve those records, withheld retrieves none. A restarted cognition owner reconstructs the same progression report without issuing another inference.

The integrated acquisition/transfer fixture passed (**1 passed in 67.56s**); changed Python compiled. This remains a deterministic fake-invoker exercise. It does not establish actual-model performance, learning, or production use.

Next: expose per-episode score deltas directly in the read-only progression report, with explicit denominators and no aggregate learning claim; test positive, adverse, unscoreable, and restored conditions.
