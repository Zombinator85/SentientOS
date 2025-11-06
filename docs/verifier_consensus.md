# Verifier Consensus Lifecycle

SentientOS coordinates verifier consensus jobs by replaying verification bundles, collecting signed votes, and aggregating them until a quorum is achieved. Recent hardening work added durable job state, restart-resume semantics, and explicit administrative controls.

## Job states

Each consensus job persists its progress under `verify/state/<job_id>.json`. The state file tracks:

- `status`: `RUNNING`, `FINALIZED`, or `CANCELED`.
- quorum configuration (`quorum_k` / `quorum_n`) and participants.
- collected votes, retry counters, and per-node error strings.
- timestamps (`started_at`, `last_update`) used for metrics and pruning.

Active jobs are fsync-ed after every vote merge so a relay restart can restore the in-flight aggregation without duplicating votes.

## Restart semantics

During relay boot the app invokes `resume_inflight_jobs()`. Any job in `RUNNING` state is rebuilt in memory, marked with a `resumed` flag, and its snapshot is broadcast over the admin SSE channel so operators can see the recovery in the console. Finalized jobs remain in the consensus archive; canceled jobs stay on disk for 24 hours before pruning.

## Administrative controls

Two authenticated endpoints complement the console buttons:

- `POST /admin/verify/consensus/cancel` – stop a job immediately. This marks the job as `CANCELED`, preserves its partial votes for review, and prevents further mesh solicitations. A safety-shadow entry is appended to the audit log with the actor and reason.
- `POST /admin/verify/consensus/finalize` – when quorum has already been met, sign and persist the consensus verdict even if retries are still pending. The request is rejected unless the quorum threshold has been satisfied.

The console exposes matching **Cancel** and **Force Finalize** buttons (CSRF guarded) that call these endpoints.

## Retry policy

Mesh solicitations honour an exponential backoff with jitter:

- Base delay 500 ms, multiplied by 1.6 for each retry.
- Random jitter in the 0–200 ms range to avoid thundering herds.
- Maximum of six attempts per participant; afterward the relay stops issuing solicitations until an operator intervenes.

Retry counters, last-error summaries, and the next retry ETA are included in the consensus SSE payload and rendered in the console. Administrators also see a resume badge when state was restored after a relay restart.

## Metrics

`memory_governor.metrics()` now reports:

- counts of running, finalized, and canceled consensus jobs,
- cumulative retry/error totals across active jobs,
- and the average time-to-quorum for finalized runs.

These additions make consensus execution observable end-to-end and resilient to relay restarts.

## Demo workflow

Operators can rehearse the full lifecycle with the sample plan in
`demos/consensus/small_plan.json`. Follow the scripted walkthrough in
[`demos/README.md`](../demos/README.md) to:

1. submit a verification job,
2. start a 2-of-3 consensus run,
3. restart the relay to watch the job resume automatically, and
4. exercise the Cancel / Force Finalize controls from the console.

The console highlights resumed jobs with a badge and streams live retry and
error details so administrators can confirm the mesh backoff policy behaves as
expected during the demo.
