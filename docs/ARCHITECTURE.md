# Architecture Overview

SentientOS is organised around the Codex autonomy loop.  The loop now combines
purposeful amendment generation, covenantal integrity checks, HungryEyes
anomaly scoring, automated test feedback, and staged commits.

## Unified Codex Amendment Pipeline

1. **GapSeeker & GenesisForge** collect TODO/FIXME markers, failing-test
   manifests, and outdated documentation hints.  Each signal becomes a
   targeted amendment proposal with a unique fingerprint so duplicate work is
   avoided.
2. **Pulse Bus** persists and signs every proposal event.  The integrity
   pipeline subscribes to these events to guarantee that every amendment is
   reviewed.
3. **Covenant IntegrityDaemon** executes proof verification and probe checks.
   Violations are quarantined with full ledger entries and remain available for
   CodexHealer triage.
4. **HungryEyes Sentinel** scores each successful proof report.  High-risk
   amendments are held for manual blessing; low-risk proposals continue to test
   execution automatically.
5. **Test Feedback Gate** runs `pytest -q` and, when available, `make ci`.  Only
   amendments that satisfy both covenant checks and tests transition to the
   "approved" state.
6. **SpecAmender Commit Strategy** batches minor maintenance approvals (default
   five-minute window) while shipping major fixes immediately with descriptive
   commit messages.  Commit timestamps are recorded so the cadence is
   observable.
7. **CodexHealer** prunes quarantined or failed amendments once their expiry
   window lapses, keeping the state lean.

The resulting lifecycle is illustrated below.

```
                   +------------------+
                   |  GenesisForge    |
                   |  (GapSeeker)     |
                   +---------+--------+
                             |
                   codex.amendment_proposed
                             v
+------------------+     dual control     +--------------------+
| Covenant checks  |--------------------->| HungryEyes Sentinel|
| (IntegrityDaemon)|                      |  (risk scoring)    |
+--------+---------+                      +----------+---------+
         |                                         |
         | ledger + proof                          |
         +-------------------+---------------------+
                             |
                verdict + risk assessment
                             v
                  Automated Test Gate
                             |
                 approved / quarantined / failed
                             |
              +--------------+---------------+
              |      SpecAmender & commits    |
              +--------------+---------------+
                             |
                       CodexHealer pruning
```

## HungryEyes Continuous Learning

The integrated integrity pipeline retrains HungryEyes every ten processed
amendments.  Ledger history, quarantine payloads, and optional simulated
negative examples (drop JSON files into
`sentientos_data/daemon/integrity/simulated_negatives/`) provide training data.
Retraining updates the sentinel in place so subsequent proposals inherit the
refined risk model without restarting the daemon.

## Commit Cadence and Batching

Approved amendments carry a priority label.  Major fixes (for example, failing
tests) are committed immediately with their proposal summary as the commit
message.  Minor maintenance items accumulate until the batching window expires
(5 minutes by default) or at least three approvals are ready, producing a
single "Codex maintenance batch" commit.  Each commit updates the Codex state so
subsequent cycles understand when the last push occurred.
