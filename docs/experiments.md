# Reflex Experiment Governance

This module introduces collaborative experimentation for reflex rules.

## Submitting Experiments

Use `experiment_cli.py propose "desc" "conditions" "expected" --user alice` to
create a new experiment. Each proposal receives a unique ID and is stored in
`logs/experiments.json`. All actions are also recorded to
`logs/experiment_audit.jsonl`.

## Voting and Comments

Participants may vote or comment on experiments using the CLI or the
`/experiments` API. Once the configured threshold of positive votes is met the
experiment status moves from `pending` to `active`.

## Live Tracking

Trigger counts and successes are recorded with `experiment_tracker.record_result`. The
CLI `list` command shows success rates so the community can decide whether to
promote a reflex to core status or adjust its parameters.

## API Usage

`experiments_api.py` exposes `/experiments` for listing and proposing experiments
and `/experiments/vote` and `/experiments/comment` for community feedback.

Permissions and authentication should be handled by the hosting application.

SentientOS prioritizes operator accountability, auditability, and safe shutdown.
